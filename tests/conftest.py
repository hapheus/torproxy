import os
import sys

# Ensure docker/ directory is on sys.path for api module import
docker_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docker"))
if docker_dir not in sys.path:
    sys.path.insert(0, docker_dir)
