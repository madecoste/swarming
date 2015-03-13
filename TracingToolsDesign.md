


# Objective #

Generate the exact list of files needed to run an executable, using automated means across multiple OSes.


# Background #

Build systems are (usually) deterministic. One tool to declare build dependencies is the [GYP language](https://code.google.com/p/gyp/), which lists all the source files and supports conditions to work with different OSes, different targets, etc. As such, it is possible to build a single source file and knowing exactly what input files need to be present to compile it.

In the case of tests, more often than not, they assume they are run directly in the directory they were built in, that is, all the source tree is available. This has huge cost, as only a tiny fraction of these files are needed, and an even a smaller fraction from the files that were built.

Generating the exact list of needed files to run a test would require an insane amount of manual work so it must be automated and work across multiple OSes.


# Overview #

  * For each OS,
    * An OS-specific tracing platform is chosen.
    * Python glue code runs an executable under the system-provided tracer.
    * Python glue code reads the trace file and generates an OS-independent data structure.
    * An API is used to manipulate this data in an almost OS-independent way.


# Detailed Design #

`trace_inputs.py` is the script that can be used directly to do the tracing or can be used as a library. This tool doesn't know of GYP or `.isolate` at all as they are generated and handled by `isolate.py`.

There is 2 important classes; `ApiBase` and `Results`.


## class `ApiBase` ##

`ApiBase` declares the common interface to trace a child process, independent of the implementation or the OS. It has a limited interface and separates the action of tracing from the action of analyzing the traces. `ApiBase.get_tracer()` returns an `ApiBase.Tracer` derived instance that manages the lifetime of the tracing infrastructure. Once tracing is done, `ApiBase.parse_log()` generates a list of Results instance.

The implementation is to use:
  * dtrace on OSX
  * "NT Kernel Logger" on Window
  * strace on linux

Much of the particularities between each implementation is described in the docstring of each implementation class. As a starter, strace is a pure user-mode tracer, while dtrace and the NT Kernel Logger are kernel-only tracers, which have no effect on the traced processes. The API hides this fact and have a consistent API across user mode and kernel mode tracers.


## class `Results` ##

`Results` holds the results of the trace. It is immutable so any mutation with one of its member function effectively create a new instance. The results contains a tree of `Results.Process` instances, each representing the root process and each child process started by the root process. Each process has a `.files` attribute that list each of the files accessed by this process.

It also contains meta data like the command line, the executable name, etc.

Every files referenced in Results is stored in its _native path case_ if the file exists at the time of log retrieval. Symlinks are not resolved.


# Project information #

This project is subsumed by Swarming.


# Caveats #

  * The implementation requires a lot of OS-specific code.
  * Some tracers still have bugs, for example the default strace version (4.5) included in Ubuntu has internal race conditions so the trace logs can be corrupted even if the test case ran properly, so the trace needs to be run a second time.
  * The D code for dtrace causes an enormous performance hit on OSX, making hardly usable.
  * The NT Kernel Logger on Windows is not 100% accurate, it occasionally list files that were not touched by the executable and the tracer itself is not logging sufficiently to output as much data than with dtrace or strace.


# Latency #

Wall time duration is reduced by tracing multiple test cases concurrently with `trace_test_cases.py`. It works seamlessly with user mode or kernel mode loggers. This significantly help on 8+ cores systems.


# Testing plan #

Testing is done in two paths:
  * Testing the code itself so its behavior corresponds to the specified design.
  * OS-specific tracing infrastructure works as intended.

For example, an OS update, like OSX 10.6 to 10.7, caused different functions to be called, which required changed to the [D code for dtrace tracing](https://developer.apple.com/library/mac/#documentation/Darwin/Reference/ManPages/man1/dtrace.1.html). The automated smoke test must be run on each of the supported platform. This is currently done manually due to the limited number of contributors.