"""Deployment targets — separate from runtimes on purpose. See `base.py`."""

from agentbridge.deploy.base import DeployCommand, DeploymentRegistry, DeploymentTarget
from agentbridge.deploy.langgraph_platform import LangGraphPlatformTarget

registry = DeploymentRegistry()
registry.register(LangGraphPlatformTarget)

__all__ = [
    "DeployCommand",
    "DeploymentRegistry",
    "DeploymentTarget",
    "LangGraphPlatformTarget",
    "registry",
]
