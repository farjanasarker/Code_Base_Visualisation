FROM python:3.12-slim

# No third-party packages — the sandbox only runs the target repo's own code
# against the stdlib. Anything importing a non-stdlib package fails inside the
# container with a clear ImportError, surfaced to the caller as
# "dependency not available in sandbox" rather than auto-installed.

COPY tracer_runner.py /sandbox/tracer_runner.py

WORKDIR /workspace
ENTRYPOINT ["python", "/sandbox/tracer_runner.py"]
