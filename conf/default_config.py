import sys
import json5
import os

# This is sloth's default configuration.
#
# The configuration file is a simple python module with module-level
# variables.  This module contains the default values for sloth's 
# configuration variables.
#
# In all cases in the configuration where a python callable (such as a
# function, class constructor, etc.) is expected, it is equally possible
# to specify a module path (as string) pointing to such a python callable.
# It will then be automatically imported.

# LABELS
#
# List/tuple of dictionaries that defines the label classes
# that are handled by sloth.  For each label, there should
# be one dictionary that contains the following keys:
#
#   - 'item' : Visualization item for this label. This can be
#              any python callable or a module path string 
#              implementing the visualization item interface.
#
#   - 'inserter' : (optional) Item inserter for this label.
#                  If the user selects to insert a new label of this class
#                  the inserter is responsible to actually 
#                  capture the users mouse actions and insert
#                  a new label into the annotation model.
#
#   - 'hotkey' : (optional) A keyboard shortcut starting 
#                the insertion of a new label of this class.
#
#   - 'attributes' : (optional) A dictionary that defines the
#                    keys and possible values of this label
#                    class.
#
#   - 'text' : (optional) A label for the item's GUI button.
print('faQ2')
print('sys.argv[0]', sys.argv[0])
# 获取这次配置文件的路径
direct = os.path.dirname(sys.argv[0])
print('sys_directory', direct)
with open(os.path.join(direct, 'sloth.txt'), 'r') as f:
    label_path = f.read()
    print('config_json', label_path)
temp = []
try:
    with open(label_path, 'r') as f:
        temp = json5.load(f)
    if not isinstance(temp, list):
        temp = []
except Exception as e:
    temp = []
    print(e)
finally:
    LABELS = temp

# HOTKEYS
#
# Defines the keyboard shortcuts.  Each hotkey is defined by a tuple
# with at least 2 entries, where the first entry is the hotkey (sequence),
# and the second entry is the function that is called.  The function
# should expect a single parameter, the labeltool object.  The optional
# third entry -- if present -- is expected to be a string describing the 
# action.
HOTKEYS = (
    ('Space', [lambda lt: lt.currentImage().confirmAll(),
               lambda lt: lt.currentImage().setUnlabeled(False),
               lambda lt: lt.gotoNext()
               ], 'Mark image as labeled/confirmed and go to next'),
    ('Backspace', lambda lt: lt.gotoPrevious(), 'Previous image/frame'),
    ('PgDown', lambda lt: lt.gotoNext(), 'Next image/frame'),
    ('PgUp', lambda lt: lt.gotoPrevious(), 'Previous image/frame'),
    ('Tab', lambda lt: lt.selectNextAnnotation(), 'Select next annotation'),
    ('Shift+Tab', lambda lt: lt.selectPreviousAnnotation(), 'Select previous annotation'),
    ('Ctrl+f', lambda lt: lt.view().fitInView(), 'Fit current image/frame into window'),
    ('Del', lambda lt: lt.deleteSelectedAnnotations(), 'Delete selected annotations'),
    ('ESC', lambda lt: lt.exitInsertMode(), 'Exit insert mode'),
    ('Shift+l', lambda lt: lt.currentImage().setUnlabeled(False), 'Mark current image as labeled'),
    ('Shift+c', lambda lt: lt.currentImage().confirmAll(), 'Mark all annotations in image as confirmed'),
)

# CONTAINERS
#
# A list/tuple of two-tuples defining the mapping between filename pattern and
# annotation container classes.  The filename pattern can contain wildcards
# such as * and ?.  The corresponding container is expected to either a python
# class implementing the sloth container interface, or a module path pointing
# to such a class.
CONTAINERS = (
    ('*.json', 'sloth.annotations.container.JsonContainer'),
    ('*.msgpack', 'sloth.annotations.container.MsgpackContainer'),
    ('*.yaml', 'sloth.annotations.container.YamlContainer'),
    ('*.pickle', 'sloth.annotations.container.PickleContainer'),
    ('*.sloth-init', 'sloth.annotations.container.FileNameListContainer'),
)

# PLUGINS
#
# A list/tuple of classes implementing the sloth plugin interface.  The
# classes can either be given directly or their module path be specified 
# as string.
PLUGINS = (
)
