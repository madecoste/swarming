# Copyright 2014 The Swarming Authors. All rights reserved.
# Use of this source code is governed by the Apache v2.0 license that can be
# found in the LICENSE file.

"""This module defines Auth Server frontend url handlers."""

import os

import webapp2

from google.appengine.api import app_identity
from google.appengine.api import users

from components import auth
from components import template
from components import utils

from components.auth import model
from components.auth import tokens
from components.auth import version
from components.auth.proto import replication_pb2
from components.auth.ui import rest_api
from components.auth.ui import ui

from common import importer
from common import replication


# Path to search for jinja templates.
TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'templates')


################################################################################
## UI handlers.


class WarmupHandler(webapp2.RequestHandler):
  def get(self):
    auth.warmup()
    self.response.headers['Content-Type'] = 'text/plain; charset=utf-8'
    self.response.write('ok')


class EmailHandler(webapp2.RequestHandler):
  """Blackhole any email sent."""
  def post(self, to):
    pass


class ConfigHandler(ui.UINavbarTabHandler):
  """Page with simple UI for service-global configuration."""
  navbar_tab_url = '/auth/config'
  navbar_tab_id = 'config'
  navbar_tab_title = 'Config'
  # config.js here won't work because there's global JS var 'config' already.
  js_file_url = '/auth_service/static/js/config_page.js'
  template_file = 'auth_service/config.html'


class ServicesHandler(ui.UINavbarTabHandler):
  """Page with management UI for linking services."""
  navbar_tab_url = '/auth/services'
  navbar_tab_id = 'services'
  navbar_tab_title = 'Services'
  js_file_url = '/auth_service/static/js/services.js'
  template_file = 'auth_service/services.html'


################################################################################
## API handlers.


class LinkTicketToken(auth.TokenKind):
  """Parameters for ServiceLinkTicket.ticket token."""
  expiration_sec = 24 * 3600
  secret_key = auth.SecretKey('link_ticket_token', scope='local')
  version = 1


class ImporterConfigHandler(auth.ApiHandler):
  """Reads and sets configuration of the group importer."""

  @auth.require(auth.is_admin)
  def get(self):
    self.send_response({'config': importer.read_config()})

  @auth.require(auth.is_admin)
  def post(self):
    config = self.parse_body().get('config')
    if not importer.is_valid_config(config):
      self.abort_with_error(400, text='Invalid config format.')
    importer.write_config(config)
    self.send_response({'ok': True})


class ServiceListingHandler(auth.ApiHandler):
  """Lists registered replicas with their state."""

  @auth.require(auth.is_admin)
  def get(self):
    services = sorted(
        replication.AuthReplicaState.query(
            ancestor=replication.replicas_root_key()),
        key=lambda x: x.key.id())
    last_auth_state = model.get_replication_state()
    self.send_response({
      'services': [
        x.to_serializable_dict(with_id_as='app_id') for x in services
      ],
      'auth_code_version': version.__version__,
      'auth_db_rev': {
        'primary_id': last_auth_state.primary_id,
        'rev': last_auth_state.auth_db_rev,
        'ts': utils.datetime_to_timestamp(last_auth_state.modified_ts),
      },
      'now': utils.datetime_to_timestamp(utils.utcnow()),
    })


class GenerateLinkingURL(auth.ApiHandler):
  """Generates an URL that can be used to link a new replica.

  See auth/proto/replication.proto for the description of the protocol.
  """

  @auth.require(auth.is_admin)
  def post(self, app_id):
    # On local dev server |app_id| may use @localhost:8080 to specify where
    # app is running.
    custom_host = None
    if utils.is_local_dev_server():
      app_id, _, custom_host = app_id.partition('@')

    # Generate an opaque ticket that would be passed back to /link_replica.
    # /link_replica will verify HMAC tag and will ensure the request came from
    # application with ID |app_id|.
    ticket = LinkTicketToken.generate([], {'app_id': app_id})

    # ServiceLinkTicket contains information that is needed for Replica
    # to figure out how to contact Primary.
    link_msg = replication_pb2.ServiceLinkTicket()
    link_msg.primary_id = app_identity.get_application_id()
    link_msg.primary_url = self.request.host_url
    link_msg.generated_by = auth.get_current_identity().to_bytes()
    link_msg.ticket = ticket

    # Special case for dev server to simplify local development.
    if custom_host:
      assert utils.is_local_dev_server()
      host = 'http://%s' % custom_host
    else:
      # Use same domain as auth_service. Usually it's just appspot.com.
      current_hostname = app_identity.get_default_version_hostname()
      domain = current_hostname.partition('.')[2]
      naked_app_id = app_id
      if ':' in app_id:
        naked_app_id = app_id[app_id.find(':')+1:]
      host = 'https://%s.%s' % (naked_app_id, domain)

    # URL to a handler on Replica that initiates Replica <-> Primary handshake.
    url = '%s/auth/link?t=%s' % (
        host, tokens.base64_encode(link_msg.SerializeToString()))
    self.send_response({'url': url}, http_code=201)


class LinkRequestHandler(auth.AuthenticatingHandler):
  """Called by a service that wants to become a Replica."""

  # Handler uses X-Appengine-Inbound-Appid header protected by GAE.
  xsrf_token_enforce_on = ()

  def reply(self, status):
    """Sends serialized ServiceLinkResponse as a response."""
    msg = replication_pb2.ServiceLinkResponse()
    msg.status = status
    self.response.headers['Content-Type'] = 'application/octet-stream'
    self.response.write(msg.SerializeToString())

  # Check that the request came from some GAE app. It filters out most requests
  # from script kiddies right away.
  @auth.require(lambda: auth.get_current_identity().is_service)
  def post(self):
    # Deserialize the body. Dying here with 500 is ok, it should not happen, so
    # if it is happening, it's nice to get an exception report.
    request = replication_pb2.ServiceLinkRequest.FromString(self.request.body)

    # Ensure the ticket was generated by us (by checking HMAC tag).
    ticket_data = None
    try:
      ticket_data = LinkTicketToken.validate(request.ticket, [])
    except tokens.InvalidTokenError:
      self.reply(replication_pb2.ServiceLinkResponse.BAD_TICKET)
      return

    # Ensure the ticket was generated for the calling application.
    replica_app_id = ticket_data['app_id']
    expected_ident = auth.Identity(auth.IDENTITY_SERVICE, replica_app_id)
    if auth.get_current_identity() != expected_ident:
      self.reply(replication_pb2.ServiceLinkResponse.AUTH_ERROR)
      return

    # Register the replica. If it is already there, will reset its known state.
    replication.register_replica(replica_app_id, request.replica_url)
    self.reply(replication_pb2.ServiceLinkResponse.SUCCESS)


################################################################################
## Application routing boilerplate.


def get_routes():
  # Use special syntax on dev server to specify where app is running.
  app_id_re = r'[0-9a-zA-Z_\-\:\.]*'
  if utils.is_local_dev_server():
    app_id_re += r'(@localhost:[0-9]+)?'

  # Auth service extends the basic UI and API provided by Auth component.
  routes = []
  routes.extend(rest_api.get_rest_api_routes())
  routes.extend(ui.get_ui_routes())
  routes.extend([
    # UI routes.
    webapp2.Route(
        r'/', webapp2.RedirectHandler, defaults={'_uri': '/auth/groups'}),
    webapp2.Route(r'/_ah/mail/<to:.+>', EmailHandler),
    webapp2.Route(r'/_ah/warmup', WarmupHandler),

    # API routes.
    webapp2.Route(
        r'/auth_service/api/v1/importer/config',
        ImporterConfigHandler),
    webapp2.Route(
        r'/auth_service/api/v1/internal/link_replica',
        LinkRequestHandler),
    webapp2.Route(
        r'/auth_service/api/v1/services',
        ServiceListingHandler),
    webapp2.Route(
        r'/auth_service/api/v1/services/<app_id:%s>/linking_url' % app_id_re,
        GenerateLinkingURL),
  ])
  return routes


def create_application(debug=False):
  replication.configure_as_primary()

  # Configure UI appearance, add all custom tabs.
  ui.configure_ui(
      app_name='Auth Service',
      ui_tabs=[
        # Standard tabs provided by auth component.
        ui.GroupsHandler,
        ui.OAuthConfigHandler,
        ui.IPWhitelistsHandler,
        # Additional tabs available only on auth service.
        ConfigHandler,
        ServicesHandler,
      ])
  template.bootstrap({'auth_service': TEMPLATES_DIR})

  # Add a fake admin for local dev server.
  if utils.is_local_dev_server():
    auth.bootstrap_group(
        auth.ADMIN_GROUP,
        [auth.Identity(auth.IDENTITY_USER, 'test@example.com')],
        'Users that can manage groups')
  return webapp2.WSGIApplication(get_routes(), debug=debug)
