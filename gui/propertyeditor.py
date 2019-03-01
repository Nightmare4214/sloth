import json
import sys

import json5
import os
import time
import logging

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import pyqtSignal, QSize, Qt, QRegExp
from PyQt4.QtGui import QWidget, QGroupBox, QVBoxLayout, QPushButton, QScrollArea, QLineEdit, QDoubleValidator, \
    QIntValidator, QShortcut, QKeySequence, QComboBox, QFileDialog, QCursor, QRegExpValidator
from sloth.annotations.container import AnnotationContainerFactory
from sloth.core.exceptions import ImproperlyConfigured
from sloth.annotations.model import AnnotationModelItem
from sloth.gui.floatinglayout import FloatingLayout
from sloth.gui.utils import MyVBoxLayout
from sloth.utils.bind import bind
import sloth.conf.default_config as cf
import sloth.Main as Main

LOG = logging.getLogger(__name__)


class AbstractAttributeHandler:
    def defaults(self):
        return {}

    def updateValues(self, values):
        pass

    def setItems(self, items, showItemClasses=False):
        pass

    def autoAddEnabled(self):
        return False


class AttributeHandlerFactory:
    def create(self, attribute, values):
        # Class attribute cannot be changed
        if attribute == 'class':
            return None

        # Just a value. No attribute editor needed, we just add it to the item to be inserted...
        if isinstance(values, str) or isinstance(values, float) or isinstance(values, int):
            return None

        # If it's already a handler, just return it
        if isinstance(values, AbstractAttributeHandler):
            return values

        # Else, we create our own default handler
        return DefaultAttributeHandler(attribute, values)


class DefaultAttributeHandler(QGroupBox, AbstractAttributeHandler):
    def __init__(self, attribute, values, parent=None):
        QGroupBox.__init__(self, attribute, parent)
        self._attribute = attribute
        self._current_items = []
        self._defaults = {}
        self._inputField = None
        self._inputFieldType = None
        self._insertIndex = -1
        self._insertAtEnd = False
        self._shortcuts = {}

        # Setup GUI
        self._layout = FloatingLayout()
        self.setLayout(self._layout)
        self._buttons = {}

        # Add interface elements
        self.updateValues(values)

    def focusInputField(self, selectInput=True):
        if self._inputField is not None:
            if selectInput:
                self._inputField.selectAll()
            self._inputField.setFocus(Qt.ShortcutFocusReason)

    def addShortcut(self, shortcut, widget, value):
        if widget is not None:
            if shortcut not in self._shortcuts:
                sc = QShortcut(QKeySequence(shortcut), self)
                self._shortcuts[shortcut] = sc
                if isinstance(widget, QPushButton):
                    sc.activated.connect(bind(lambda w: w.click() if not w.isChecked() else None, widget))
                elif isinstance(widget, QLineEdit):
                    sc.activated.connect(self.focusInputField)
            else:
                raise ImproperlyConfigured("Shortcut '%s' defined more than once" % shortcut)
        else:
            raise ImproperlyConfigured("Shortcut '%s' defined for value '%s' which is hidden" % (shortcut, value))

    def updateValues(self, values):
        if isinstance(values, type):
            self.addInputField(values)
        else:
            for val in values:
                v = val
                shortcut = None
                widget = None

                # Handle the case of the value being a 2-tuple consisting of (value, shortcut)
                if type(val) is tuple or type(val) is list:
                    if len(val) == 2:
                        v = val[0]
                        shortcut = val[1]
                    else:
                        raise ImproperlyConfigured(
                            "Values must be types, strings, numbers, or tuples of length 2: '%s'" % str(val))

                # Handle the case where value is a Python type
                if isinstance(v, type):
                    if v is float or v is int or v is str:
                        self.addInputField(v)
                        widget = self._inputField
                    else:
                        raise ImproperlyConfigured("Input field with type '%s' not supported" % v)

                # * marks the position where buttons for new values will be insered
                elif val == "*" or val == "<*":
                    self._insertIndex = self._layout.count()
                elif val == "*>":
                    self._insertIndex = self._layout.count()
                    self._insertAtEnd = True

                # Add the value button
                else:
                    self.addValue(v)
                    widget = self._buttons[v]

                # If defined, add the specified shortcut
                if shortcut is not None:
                    self.addShortcut(shortcut, widget, v)

    def defaults(self):
        return self._defaults

    def autoAddEnabled(self):
        return self._insertIndex >= 0

    def onInputFieldReturnPressed(self):
        val = str(self._inputField.text())
        self.addValue(val, True)
        for item in self._current_items:
            item[self._attribute] = val
        self.updateButtons()
        self.updateInputField()
        self._inputField.clearFocus()

    def addInputField(self, _type):
        if self._inputField is None:
            self._inputFieldType = _type
            self._inputField = QLineEdit()
            if _type is float:
                self._inputField.setValidator(QDoubleValidator())
            elif _type is int:
                self._inputField.setValidator(QIntValidator())

            self._layout.addWidget(self._inputField)
            self._inputField.returnPressed.connect(self.onInputFieldReturnPressed)
        elif self._inputFieldType is not _type:
            raise ImproperlyConfigured("Input field for attribute '%s' configured twice with different types %s != %s" \
                                       % (self._attribute, self._inputFieldType, _type))

    def addValue(self, v, autoAddValue=False):
        if v in self._buttons: return
        if autoAddValue and self._insertIndex < 0: return
        button = QPushButton(v, self)
        button.setFlat(True)
        button.setCheckable(True)
        self._buttons[v] = button
        if autoAddValue:
            self._layout.insertWidget(self._insertIndex, button)
            if self._insertAtEnd:
                self._insertIndex += 1
        else:
            self._layout.addWidget(button)
        button.clicked.connect(bind(self.onButtonClicked, v))

    def reset(self):
        self._current_items = []
        for v, button in self._buttons.items():
            button.setChecked(False)
            button.setFlat(True)

    def getSelectedValues(self):
        return set([str(item[self._attribute]) for item in self._current_items if
                    self._attribute in item and item[self._attribute] is not None])

    def updateInputField(self):
        if self._inputField is not None:
            self._inputField.clear()
            selected_values = self.getSelectedValues()
            if len(selected_values) > 1:
                self._inputField.setPlaceholderText(", ".join(selected_values))
            elif len(selected_values) == 1:
                it = iter(selected_values)
                self._inputField.setText(next(it))

    def updateButtons(self):
        selected_values = self.getSelectedValues()
        for val, button in self._buttons.items():
            if val in selected_values:
                if len(selected_values) > 1:
                    button.setFlat(False)
                    button.setChecked(False)
                else:
                    button.setFlat(True)
                    button.setChecked(True)
            else:
                button.setFlat(True)
                button.setChecked(False)

    def setItems(self, items, showItemClasses=False):
        self.reset()
        if showItemClasses:
            title = ", ".join(set([item['class'] for item in items]))
            self.setTitle(self._attribute + " (" + title + ")")
        else:
            self.setTitle(self._attribute)

        self._current_items = items

        self.updateButtons()
        self.updateInputField()

    def onButtonClicked(self, val):
        attr = self._attribute
        LOG.debug("Button %s: %s clicked" % (attr, val))
        button = self._buttons[val]

        # Update model item
        for item in self._current_items:
            if button.isChecked():
                item[attr] = val
            else:
                item[attr] = None

        # Unpress all other buttons
        for v, but in self._buttons.items():
            but.setFlat(True)
            if but is not button:
                but.setChecked(False)

        # Update input field
        self.updateInputField()


class LabelEditor(QScrollArea):
    def __init__(self, items, parent, insertionMode=False):
        QScrollArea.__init__(self, parent)
        self._editor = parent
        self._items = items
        self._insertion_mode = insertionMode

        # Find all classes
        self._label_classes = set([item['class'] for item in items if 'class' in item])
        n_classes = len(self._label_classes)
        LOG.debug("Creating editor for %d item classes: %s" % (n_classes, ", ".join(list(self._label_classes))))

        # Widget layout
        self._layout = QVBoxLayout()
        self._content = QWidget()
        self._content.setLayout(self._layout)

        attributes = set()
        for lc in self._label_classes:
            attributes |= set(self._editor.getLabelClassAttributes(lc))

        attributes = list(attributes)
        attributes.sort()
        for attr in attributes:
            handler = self._editor.getHandler(attr)
            if handler is not None:
                if len(items) > 1:
                    valid_items = [item for item in items
                                   if attr in self._editor.getLabelClassAttributes(item['class'])]
                    handler.setItems(valid_items, True)
                else:
                    handler.setItems(items)
                self._layout.addWidget(handler)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setWidget(self._content)

    def sizeHint(self):
        minsz = self.minimumSize()
        sz = self._layout.minimumSize()
        left, top, right, bottom = self.getContentsMargins()
        return QSize(max(minsz.width(), sz.width() + left + right), max(minsz.height(), sz.height() + top + bottom))

    def labelClasses(self):
        return self._label_classes

    def currentProperties(self):
        if len(self._items) == 1:
            return self._items[0]
        else:
            return {}

    def insertionMode(self):
        return self._insertion_mode


class PropertyEditor(QWidget):
    # Signals
    insertionModeStarted = pyqtSignal(str)
    insertionModeEnded = pyqtSignal()
    insertionPropertiesChanged = pyqtSignal(object)
    editPropertiesChanged = pyqtSignal(object)

    def __init__(self, config, parent=None):
        QWidget.__init__(self, parent)
        self._class_config = {}
        self._class_items = {}
        self._class_prototypes = {}
        self._attribute_handlers = {}
        self._handler_factory = AttributeHandlerFactory()

        self._setupGUI()
        # Add label classes from config
        for label in config:
            self.addLabelClass(label)

    def onModelChanged(self, new_model):
        attrs = set([k for k, v in self._attribute_handlers.items() if v.autoAddEnabled()])
        if len(attrs) > 0:
            start = time.time()
            attr2vals = {}
            for item in new_model.iterator(AnnotationModelItem):
                for attr in attrs:
                    if attr in item:
                        if attr not in attr2vals:
                            attr2vals[attr] = set((item[attr],))
                        else:
                            attr2vals[attr] |= set((item[attr],))
            diff = time.time() - start
            LOG.info("Extracted annotation values from model in %.2fs" % diff)
            for attr, vals in attr2vals.items():
                h = self._attribute_handlers[attr]
                for val in vals:
                    h.addValue(val, True)

    # 设置右键菜单所在位置
    def showContextMenu(self, label_class):
        self._class_context[label_class].exec_(QCursor.pos())

    # 删除标签
    def remove_item(self, label_class):
        print(label_class)
        try:
            # 删除
            if label_class in self._class_shortcuts:
                del self._class_shortcuts[label_class]
            del self._class_context[label_class]
            del self._class_action[label_class]
            self._classbox_layout.removeWidget(self._class_buttons[label_class])
            self._class_buttons[label_class].deleteLater()
            self._class_buttons[label_class] = None
            del self._class_config[label_class]
            # 写回json
            direct = os.path.dirname(sys.argv[0])
            with open(os.path.join(direct, 'sloth.txt'), 'r') as f:
                label_path = f.read()
            try:
                with open(label_path, 'r') as f:
                    temp = json5.load(f)
                for i, current_json in enumerate(temp):
                    if current_json['attributes']['class'] == label_class:
                        temp.remove(current_json)
                        # 遍历combo box 找到要删的
                        for i in range(len(self.combo_box)):
                            current_label = self.combo_box.itemText(i)
                            if current_label == label_class:
                                print('removed', label_class)
                                self.combo_box.removeItem(i)
                                break
                        break
                with open(label_path, 'w') as f:
                    json5.dump(temp, f, indent=4, separators=(',', ': '), sort_keys=True, ensure_ascii=False)

            except Exception as e:
                print(e)
        except Exception as e:
            print(e)

    def addLabelClass(self, label_config):
        # Check label configuration
        if 'attributes' not in label_config:
            raise ImproperlyConfigured("Label with no 'attributes' dict found")
        attrs = label_config['attributes']
        if 'class' not in attrs:
            raise ImproperlyConfigured("Labels must have an attribute 'class'")
        label_class = attrs['class']
        if label_class in self._class_config:
            raise ImproperlyConfigured("Label with class '%s' defined more than once" % label_class)

        # Store config
        self._class_config[label_class] = label_config

        # Parse configuration and create handlers and item
        self.parseConfiguration(label_class, label_config)

        # Add label class button
        button_text = label_config['text']
        button = QPushButton(button_text, self)
        button.setCheckable(True)
        button.setFlat(True)
        button.clicked.connect(bind(self.onClassButtonPressed, label_class))
        self._class_buttons[label_class] = button
        self._classbox_layout.addWidget(button)

        # 添加右键菜单
        self._class_context[label_class] = QtGui.QMenu(self)
        self._class_action[label_class] = self._class_context[label_class].addAction('删除')
        self._class_action[label_class].triggered.connect(bind(self.remove_item, label_class))
        self._class_buttons[label_class].setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self._class_buttons[label_class].customContextMenuRequested.connect(bind(self.showContextMenu, label_class))

        # Add hotkey
        if 'hotkey' in label_config:
            hotkey = QShortcut(QKeySequence(label_config['hotkey']), self)
            hotkey.activated.connect(button.click)
            self._class_shortcuts[label_class] = hotkey

    def parseConfiguration(self, label_class, label_config):
        attrs = label_config['attributes']

        # Add prototype item for insertion
        self._class_items[label_class] = AnnotationModelItem({'class': label_class})

        # Create attribute handler widgets or update their values
        for attr, vals in attrs.items():
            if attr in self._attribute_handlers:
                self._attribute_handlers[attr].updateValues(vals)
            else:
                handler = self._handler_factory.create(attr, vals)
                if handler is None:
                    self._class_items[label_class][attr] = vals
                else:
                    self._attribute_handlers[attr] = handler

        for attr in attrs:
            if attr in self._attribute_handlers:
                self._class_items[label_class].update(self._attribute_handlers[attr].defaults())

    def getHandler(self, attribute):
        if attribute in self._attribute_handlers:
            return self._attribute_handlers[attribute]
        else:
            return None

    def getLabelClassAttributes(self, label_class):
        return self._class_config[label_class]['attributes'].keys()

    def onClassButtonPressed(self, label_class):
        if self._class_buttons[label_class].isChecked():
            self.startInsertionMode(label_class)
        else:
            self.endInsertionMode()

    def startInsertionMode(self, label_class):
        self.endInsertionMode(False)
        for lc, button in self._class_buttons.items():
            button.setChecked(lc == label_class)
        LOG.debug("Starting insertion mode for %s" % label_class)
        self._label_editor = LabelEditor([self._class_items[label_class]], self, True)
        self._layout.insertWidget(1, self._label_editor, 0)
        self.insertionModeStarted.emit(label_class)

    def endInsertionMode(self, uncheck_buttons=True):
        if self._label_editor is not None:
            LOG.debug("Ending insertion/edit mode")
            self._label_editor.hide()
            self._layout.removeWidget(self._label_editor)
            self._label_editor = None
            if uncheck_buttons:
                self.uncheckAllButtons()
            self.insertionModeEnded.emit()

    def uncheckAllButtons(self):
        for lc, button in self._class_buttons.items():
            button.setChecked(False)

    def markEditButtons(self, label_classes):
        for lc, button in self._class_buttons.items():
            button.setFlat(lc not in label_classes)

    def currentEditorProperties(self):
        if self._label_editor is None:
            return None
        else:
            return self._label_editor.currentProperties()

    def startEditMode(self, model_items):
        # If we're in insertion mode, ignore empty edit requests
        if self._label_editor is not None and self._label_editor.insertionMode() \
                and len(model_items) == 0:
            return

        self.endInsertionMode()
        LOG.debug("Starting edit mode for items: %s" % model_items)
        self._label_editor = LabelEditor(model_items, self)
        self.markEditButtons(self._label_editor.labelClasses())
        self._layout.insertWidget(1, self._label_editor, 0)

    # 添加txt
    def add_txt(self):
        defect = self.combo_box.currentText()
        if defect is None or defect == '':
            return
        dir_path = QFileDialog.getExistingDirectory(self)
        Main.write_txt(dir_path, {defect}, 'defect')

    # 从labeltool中设置搜索按钮
    def setFunction(self, func):
        self._search_btn.clicked.connect(func)

    # 获得关键字
    def get_key_word(self):
        key_word = self._key_word.text()
        if key_word is None or key_word == '':
            key_word = self._key_word.placeholderText()
        return key_word

    # 获得文件类型
    def get_extension(self):
        extension = self._extension.text()
        # 为空则用默认的，否则用输入的
        if extension is None or extension == '':
            extension = self._extension.placeholderText()
        return extension

    # 返回一个含有权限类型的list
    def get_attributes_type(self):
        '''
        'Rect':('sloth.items.RectItem','sloth.items.RectItemInserter'),
        'Point':('sloth.items.PointItem','sloth.items.PointItemInserter'),
        'Polygon':('sloth.items.PolygonItem','sloth.items.PolygonItemInserter')
        '''
        return ['Rect', 'Point', 'Polygon']

    # 写回json
    def rewrite_json(self, temp_json):
        # json所在的txt
        direct = os.path.dirname(sys.argv[0])
        with open(os.path.join(direct, 'sloth.txt'), 'r') as f:
            label_path = f.read()
        try:
            # 读取旧json
            with open(label_path, 'r') as f:
                temp = json5.load(f)
            # 追加我们要写入的json
            temp.append(temp_json)
            # 写入
            with open(label_path, 'w') as f:
                json5.dump(temp, f, indent=4, separators=(',', ': '), sort_keys=True, ensure_ascii=False)
        except Exception as e:
            print(e)

    # 添加标签
    def add_attributes(self):
        print('faQ_add_attributes')
        # 转换dict
        type_dict = {'Rect': ('sloth.items.RectItem', 'sloth.items.RectItemInserter'),
                     'Point': ('sloth.items.PointItem', 'sloth.items.PointItemInserter'),
                     'Polygon': ('sloth.items.PolygonItem', 'sloth.items.PolygonItemInserter')}
        # 获取添加的标签信息
        attributes = {'class': self.attributes_LineEdit.text()}
        attributes_item, attributes_inserter = type_dict[self.attributes_type.currentText()]
        attributes_hotkey = self.hotkey.text()
        attributes_text = self.text_LineEdit.text()
        temp_json = {'attributes': attributes, 'inserter': attributes_inserter,
                     'item': attributes_item,
                     'text': attributes_text}
        # 快捷键
        if attributes_hotkey is not None and attributes_hotkey != '':
            temp_json['hotkey'] = attributes_hotkey
        print(temp_json)
        try:
            # 加入标签
            self.addLabelClass(temp_json)
            print(self._class_buttons.keys())
            # 注册
            self._register('inserter', temp_json['attributes']['class'], temp_json['inserter'])
            self._register('item', temp_json['attributes']['class'], temp_json['item'])
            # add_txt的下拉框里也要添加
            self.combo_box.addItem(temp_json['attributes']['class'])
            # 写回json
            self.rewrite_json(temp_json)
        except Exception as e:
            print(e)

    def _setupGUI(self):
        self._class_buttons = {}
        self._class_shortcuts = {}
        self._class_context = {}
        self._class_action = {}
        self._label_editor = None

        # Label class buttons
        self._classbox = QGroupBox("Labels", self)
        self._classbox_layout = FloatingLayout()
        self._classbox.setLayout(self._classbox_layout)

        # 添加txt模块
        self.combo_box = QComboBox()
        self._group_box = QGroupBox('add_txt', self)
        self._group_box_layout = QVBoxLayout()
        self._group_box.setLayout(self._group_box_layout)
        temp = cf.LABELS
        items = []
        # 获取所有的标签
        for i in temp:
            items.append(i['attributes']['class'])
        # 假如下拉框
        self.combo_box.addItems(items)
        self.add_txt_btn = QPushButton('add txt')
        self.add_txt_btn.clicked.connect(self.add_txt)
        # 加入下拉框和按钮
        self._group_box_layout.addWidget(self.combo_box, 0)
        self._group_box_layout.addWidget(self.add_txt_btn, 1)

        # 根据关键字搜索图片模块
        self._group_box2 = QGroupBox('add files', self)
        # 文件名包含的
        self._key_word = QLineEdit('')
        self._key_word.setPlaceholderText('merge')
        # 文件类型
        self._extension = QLineEdit('')
        self._extension.setPlaceholderText('bmp')
        self._search_btn = QPushButton('search files')
        self._group_box_layout2 = QVBoxLayout()
        # 加入控件
        self._group_box_layout2.addWidget(self._key_word, 0)
        self._group_box_layout2.addWidget(self._extension, 1)
        self._group_box_layout2.addWidget(self._search_btn, 2)
        self._group_box2.setLayout(self._group_box_layout2)

        # 添加标签模块
        self._group_box_add_label = QGroupBox("添加标签", self)
        self._add_label_group_layout = QVBoxLayout()
        self._group_box_add_label.setLayout(self._add_label_group_layout)
        # 标签的class
        self.attributes_LineEdit = QLineEdit('')
        self.attributes_LineEdit.setPlaceholderText('attributes')
        # 标签画出来的类型
        self.attributes_type = QComboBox()
        self.attributes_type.addItems(self.get_attributes_type())
        # 快捷键，目前设置了只允许一个键
        self.hotkey = QLineEdit('')
        self.hotkey.setPlaceholderText('hotkey')
        self.regx = QRegExp("[a-z0-9]$")
        self.validator = QRegExpValidator(self.regx, self.hotkey)
        self.hotkey.setValidator(self.validator)
        # 标签显示
        self.text_LineEdit = QLineEdit('')
        self.text_LineEdit.setPlaceholderText('text')
        # 按钮
        self.attributes_add_btn = QPushButton('添加标签')
        self.attributes_add_btn.clicked.connect(self.add_attributes)
        # 假如控件
        self._add_label_group_layout.addWidget(self.attributes_LineEdit, 0)
        self._add_label_group_layout.addWidget(self.attributes_type, 1)
        self._add_label_group_layout.addWidget(self.hotkey, 2)
        self._add_label_group_layout.addWidget(self.text_LineEdit, 3)
        self._add_label_group_layout.addWidget(self.attributes_add_btn, 4)

        # Global widget
        self._layout = MyVBoxLayout()
        self.setLayout(self._layout)
        self._layout.addWidget(self._classbox, 0)
        self._layout.addStretch(1)
        self._layout.addWidget(self._group_box_add_label, 1)
        self._layout.addWidget(self._group_box, 2)
        self._layout.addWidget(self._group_box2, 3)
