"""
Plugin architecture for CSV Visualizer.

Plugins can extend the app with:
- Custom insight generators
- Custom chart types
- Data transformers (pre/post processing)
- Export formats

Plugins are discovered via:
1. Python entry points (group: 'csvviz.plugins')
2. Files in the plugins/ directory
3. Manual registration via register_plugin()
"""
import importlib
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class Plugin:
    name: str
    version: str = '0.1.0'
    description: str = ''
    author: str = ''
    hooks: dict = field(default_factory=dict)
    enabled: bool = True


# Hook types that plugins can register
HOOK_TYPES = {
    'insight_generator': 'Generate additional insights from a DataFrame',
    'chart_generator': 'Suggest additional chart configurations',
    'data_transformer': 'Transform data before analysis',
    'export_format': 'Add custom export format',
    'column_detector': 'Add custom column type detection',
    'pre_upload': 'Run before file is processed',
    'post_upload': 'Run after file is processed',
}

# Global plugin registry
_plugins = {}
_hooks = {hook: [] for hook in HOOK_TYPES}


def register_plugin(plugin):
    """Register a plugin and its hooks."""
    if plugin.name in _plugins:
        logger.warning('Plugin %s already registered, skipping', plugin.name)
        return False

    _plugins[plugin.name] = plugin

    for hook_name, callback in plugin.hooks.items():
        if hook_name in _hooks:
            _hooks[hook_name].append({
                'plugin': plugin.name,
                'callback': callback,
            })
            logger.info('Plugin %s registered hook: %s', plugin.name, hook_name)
        else:
            logger.warning('Plugin %s tried to register unknown hook: %s', plugin.name, hook_name)

    logger.info('Registered plugin: %s v%s', plugin.name, plugin.version)
    return True


def unregister_plugin(name):
    """Remove a plugin and all its hooks."""
    plugin = _plugins.pop(name, None)
    if not plugin:
        return False

    for hook_name in _hooks:
        _hooks[hook_name] = [h for h in _hooks[hook_name] if h['plugin'] != name]

    logger.info('Unregistered plugin: %s', name)
    return True


def get_plugins():
    """List all registered plugins."""
    return [
        {
            'name': p.name,
            'version': p.version,
            'description': p.description,
            'author': p.author,
            'enabled': p.enabled,
            'hooks': list(p.hooks.keys()),
        }
        for p in _plugins.values()
    ]


def get_hook_types():
    """List available hook types."""
    return HOOK_TYPES


def run_hooks(hook_name, *args, **kwargs):
    """Execute all registered callbacks for a hook. Returns list of results."""
    if hook_name not in _hooks:
        return []

    results = []
    for entry in _hooks[hook_name]:
        plugin = _plugins.get(entry['plugin'])
        if not plugin or not plugin.enabled:
            continue
        try:
            result = entry['callback'](*args, **kwargs)
            if result is not None:
                results.append({
                    'plugin': entry['plugin'],
                    'result': result,
                })
        except Exception as e:
            logger.error('Plugin %s hook %s failed: %s', entry['plugin'], hook_name, e)

    return results


def discover_entry_points():
    """Discover plugins via Python entry points (setuptools/pip installed)."""
    try:
        if sys.version_info >= (3, 12):
            from importlib.metadata import entry_points
            eps = entry_points(group='csvviz.plugins')
        else:
            from importlib.metadata import entry_points
            all_eps = entry_points()
            eps = all_eps.get('csvviz.plugins', [])

        for ep in eps:
            try:
                plugin_factory = ep.load()
                plugin = plugin_factory()
                if isinstance(plugin, Plugin):
                    register_plugin(plugin)
            except Exception as e:
                logger.warning('Failed to load entry point %s: %s', ep.name, e)
    except Exception as e:
        logger.debug('Entry point discovery skipped: %s', e)


def discover_directory(plugins_dir):
    """Discover plugins from a directory of Python files."""
    if not os.path.isdir(plugins_dir):
        return

    sys.path.insert(0, plugins_dir)
    try:
        for fname in sorted(os.listdir(plugins_dir)):
            if not fname.endswith('.py') or fname.startswith('_'):
                continue
            module_name = fname[:-3]
            try:
                mod = importlib.import_module(module_name)
                if hasattr(mod, 'create_plugin'):
                    plugin = mod.create_plugin()
                    if isinstance(plugin, Plugin):
                        register_plugin(plugin)
            except Exception as e:
                logger.warning('Failed to load plugin %s: %s', fname, e)
    finally:
        sys.path.remove(plugins_dir)


def discover_all(app_config):
    """Run all discovery mechanisms."""
    discover_entry_points()

    plugins_dir = app_config.get('PLUGINS_FOLDER')
    if plugins_dir:
        discover_directory(plugins_dir)
