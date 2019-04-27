import sys
import json5
import os
import time
import logging
from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import pyqtSignal, QSize, Qt, QRegExp
from PyQt4.QtGui import QWidget, QGroupBox, QVBoxLayout, QPushButton, QScrollArea, QLineEdit, QDoubleValidator, \
    QIntValidator, QShortcut, QKeySequence, QComboBox, QFileDialog, QCursor, QRegExpValidator, QDialog
from sloth.core.exceptions import ImproperlyConfigured
from sloth.annotations.model import AnnotationModelItem
from sloth.gui.floatinglayout import FloatingLayout
from sloth.gui.utils import MyVBoxLayout
from sloth.utils.bind import bind
import sloth.conf.default_config as cf
import sloth.Main as Main
import sloth.ExtractSegSample as ex
import copy

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


class InitSelectDialog(QDialog):
    def __init__(self, func, parent=None):
        super(InitSelectDialog, self).__init__(parent)
        self.func = func
        self.setupUi()

    def get_state(self):
        cnt = 0
        state = {}
        for k, v in self.class_check.items():
            if v.isChecked():
                cnt += 1
                state[k] = cnt
            else:
                state[k] = 0
        return state

    def setupUi(self):
        layout = QVBoxLayout()
        self.setLayout(layout)
        json_conf = Main.get_json()
        label_list = []
        for current_json in json_conf:
            label_list.append(current_json['attributes']['class'])

        self._parea = QWidget()
        self._classbox = QScrollArea()
        self._classbox_layout = QVBoxLayout()
        self._parea.setLayout(self._classbox_layout)
        self._parea.setGeometry(0, 0, len(label_list) * 35, 400)
        self._classbox.setWidget(self._parea)
        self._classbox.setGeometry(0, 0, 200, 300)

        layout.addWidget(self._classbox)

        self.class_check = {}
        for label in label_list:
            self.class_check[label] = QtGui.QCheckBox(label)
            self._classbox_layout.addWidget(self.class_check[label])

        self.ok_btn = QPushButton('确认')
        self.ok_btn.clicked.connect(self.close)
        layout.addWidget(self.ok_btn)

    # 关闭事件
    def closeEvent(self, event):
        reply = QtGui.QMessageBox.question(self,
                                           "确认",
                                           "确定好了吗",
                                           QtGui.QMessageBox.Yes | QtGui.QMessageBox.No | QtGui.QMessageBox.Cancel)
        if reply == QtGui.QMessageBox.Yes:
            self.func(self.get_state())
        elif reply == QtGui.QMessageBox.No:
            self.func(None)
        else:
            event.ignore()


# 批量修改对话框
class MultiSelectDialog(QDialog):
    def __init__(self, label_list, setGray, parent=None):
        super(MultiSelectDialog, self).__init__(parent)
        self.setGray = setGray
        self.label_list = label_list
        self.setupUi(label_list)

    # 批量修改
    def all_modify(self):
        temp = {}
        # 获取spin的值
        v = self.spin_box.value()
        for label in self.label_list:
            if self.class_check[label].isChecked():
                temp[label] = v
        self.setGray(temp)

    def all_check(self):
        for v in self.class_check.values():
            v.stateChanged.disconnect()
            v.setChecked(self.all_check_box.isChecked())
            v.stateChanged.connect(self.change_all)

    def change_all(self):
        for v in self.class_check.values():
            if not v.isChecked():
                self.all_check_box.stateChanged.disconnect()
                self.all_check_box.setChecked(False)
                self.all_check_box.stateChanged.connect(self.all_check)
                return
        self.all_check_box.setChecked(True)

    def setupUi(self, label_list):
        self.setWindowTitle('批量修改')

        layout = QVBoxLayout()
        self.setLayout(layout)
        temp_layout = QtGui.QHBoxLayout()
        self.spin_box = QtGui.QSpinBox()
        self.spin_box.setMinimum(0)
        self.spin_box.setMaximum(255)
        self.modify_btn = QPushButton('批量修改')
        self.modify_btn.clicked.connect(self.all_modify)
        temp_layout.addWidget(self.spin_box)
        temp_layout.addWidget(self.modify_btn)
        layout.addLayout(temp_layout)
        self.all_check_box = QtGui.QCheckBox('全选')
        self.all_check_box.stateChanged.connect(self.all_check)
        layout.addWidget(self.all_check_box)

        self._parea = QWidget()
        self._classbox = QScrollArea()
        self._classbox_layout = QVBoxLayout()
        self._parea.setLayout(self._classbox_layout)
        self._parea.setGeometry(0, 0, len(label_list) * 50, 300)
        self._classbox.setWidget(self._parea)
        self._classbox.setGeometry(0, 0, 200, 200)

        layout.addWidget(self._classbox)

        self.class_check = {}
        for label in label_list:
            self.class_check[label] = QtGui.QCheckBox(label)
            self._classbox_layout.addWidget(self.class_check[label])
            self.class_check[label].stateChanged.connect(self.change_all)


# 训练对话框
class TrainDialog(QDialog):
    def __init__(self, parent=None):
        super(TrainDialog, self).__init__(parent)
        self.setupUi()

    # 选择图片
    def select_image(self):
        image_types = ['*.jpg', '*.bmp', '*.png', '*.pgm', '*.ppm', '*.tiff', '*.tif', '*.gif']
        format_str = ' '.join(image_types)
        fname = QFileDialog.getOpenFileName(self, "select training source", '.',
                                            "Media files (%s)" % (format_str,))
        if fname is None or fname == '':
            return
        self.image_path = os.path.abspath(fname)
        self._image_label.setText(os.path.basename(self.image_path))

    # 选择目录
    def select_directory(self):
        directory = QFileDialog.getExistingDirectory(self)
        if directory is None:
            return
        self._collect_label.setText(directory)

    # 生成数据
    def generate(self):
        # 训练源
        search_name = self._image_label.text()
        if search_name is None or search_name == '':
            return
        # 生成目录
        search_dir = self._collect_label.text()
        if search_dir is None or search_dir == '':
            return
        # 训练集所占比例
        split_ratio = self._spin_box.value() / 100
        # 是否打乱
        do_shuffle = self._shuffle.isChecked()
        # 是否乘255/max
        multiply_flag = self._multiply.isChecked()
        # 允许全零的图
        enable_all_zero = self._enable_zero.isChecked()
        save_dir = QFileDialog.getExistingDirectory(self)
        if save_dir == '':
            return
        class2label = {}
        for k, v in self.class_text.items():
            if v == 0:
                continue
            class2label[k] = v.value()
        ex.generate_sample(search_dir, search_name, save_dir, class2label, self.class2item,
                           split_ratio=split_ratio, do_shuffle=do_shuffle, multiply_flag=multiply_flag,
                           enable_all_zero=enable_all_zero)

    def get_init_data(self, temp):
        self.init_dict=temp

    def get_init(self):
        temp = InitSelectDialog(self.get_init_data, self)
        temp.exec_()

    # 批量修改
    def modify(self):
        temp = MultiSelectDialog(self.label_list, self.setGray, self)
        temp.exec_()

    def setGray(self, temp_gray):
        for k, v in temp_gray.items():
            self.class_text[k].setValue(v)

    def setupUi(self):
        self.get_init()

        self.setWindowTitle('训练数据生成')
        self._train_layout = QVBoxLayout()
        self.setLayout(self._train_layout)

        # 训练源
        self._image_layout = QtGui.QHBoxLayout()
        self._image_layout.addWidget(QtGui.QLabel('训练源：'))
        self._image_label = QLineEdit('test.jpg')
        self._image_layout.addWidget(self._image_label)
        # 采图夹
        self._collect_layout = QtGui.QHBoxLayout()
        self._collect_layout.addWidget(QtGui.QLabel('采图夹：'))
        self._collect_label = QtGui.QLabel('')
        self._collect_btn = QPushButton('...')
        self._collect_btn.clicked.connect(self.select_directory)
        self._collect_layout.addWidget(self._collect_label)
        self._collect_layout.addWidget(self._collect_btn)
        # 训练集占比
        self._spin_box = QtGui.QDoubleSpinBox()
        self._spin_box.setMaximum(100)
        self._spin_box.setValue(80.0)

        self.modify_btn = QPushButton('批量修改灰度值')
        self.modify_btn.clicked.connect(self.modify)

        # 是否随机打乱
        self._shuffle = QtGui.QCheckBox("随机")
        # 等分
        self._multiply = QtGui.QCheckBox("255 / max(class2label.values())")
        # 允许全0的图片
        self._enable_zero = QtGui.QCheckBox('允许全0的图片')
        # 选择文件夹
        self._file_button = QPushButton('生成')
        self._file_button.clicked.connect(self.generate)

        # 加入训练源
        self.temp_Widget = QWidget()
        self.temp_Widget.setLayout(self._image_layout)
        self._train_layout.addWidget(self.temp_Widget)
        # 加入采图夹
        self.collect_Widget = QWidget()
        self.collect_Widget.setLayout(self._collect_layout)
        self._train_layout.addWidget(self.collect_Widget)

        self._train_layout.addWidget(self._spin_box)
        self._train_layout.addWidget(self.modify_btn)
        self._train_layout.addWidget(self._shuffle)
        self._train_layout.addWidget(self._multiply)
        self._train_layout.addWidget(self._enable_zero)
        self._train_layout.addWidget(self._file_button)

        self.label_list = []
        json_conf = Main.get_json()
        # 缺陷对应图形
        self.class2item = {}
        # 缺陷的数值
        self.class_text = {}

        self._parea = QWidget()
        self._classbox = QScrollArea()
        self._classbox_layout = QVBoxLayout()
        self._parea.setLayout(self._classbox_layout)
        self._parea.setGeometry(0, 0, len(json_conf) * 35, 400)
        self._classbox.setWidget(self._parea)
        self._classbox.setGeometry(0, 0, 200, 300)

        self._train_layout.addWidget(self._classbox)

        for i, current_json in enumerate(json_conf):
            temp_class = current_json['attributes']['class']
            self.label_list.append(temp_class)
            self.class2item[temp_class] = current_json['item'].split('.')[-1]
            temp_layout = QtGui.QHBoxLayout()
            temp_layout.addWidget(QtGui.QLabel(temp_class))
            self.class_text[temp_class] = QtGui.QSpinBox()
            self.class_text[temp_class].setMinimum(0)
            self.class_text[temp_class].setMaximum(255)
            if self.init_dict is None:
                self.class_text[temp_class].setValue(i + 1)
            else:
                self.class_text[temp_class].setValue(self.init_dict[temp_class])
            temp_layout.addWidget(self.class_text[temp_class])
            self._classbox_layout.addLayout(temp_layout)


brush2idx = {'Qt.NoBrush': 0,
             'Qt.SolidPattern': 1,
             'Qt.Dense1Pattern': 2,
             'Qt.Dense2Pattern': 3,
             'Qt.Dense3Pattern': 4,
             'Qt.Dense4Pattern': 5,
             'Qt.Dense5Pattern': 6,
             'Qt.Dense6Pattern': 7,
             'Qt.Dense7Pattern': 8,
             'Qt.HorPattern': 9,
             'Qt.VerPattern': 10,
             'Qt.CrossPattern': 11,
             'Qt.BDiagPattern': 12,
             'Qt.FDiagPattern': 13,
             'Qt.DiagCrossPattern': 14,
             'Qt.LinearGradientPattern': 15,
             'Qt.RadialGradientPattern': 16,
             'Qt.ConicalGradientPattern': 17}


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
        self._parea.setGeometry(0, 0, 200, 0)
        # Add label classes from config
        for label in config:
            self.addLabelClass(label)
        self.image_path = None

    def addLabelClassByPath(self, configs_path):
        # 读配置文件
        with open(configs_path, 'r') as f:
            configs = json5.load(f)
        # 写入当前配置文件的路径
        direct = os.path.dirname(sys.argv[0])
        with open(os.path.join(direct, 'sloth.txt'), 'w') as f:
            f.write(configs_path)
        self._parea.setGeometry(0, 0, 200, 0)
        for temp_json in configs:
            self.addLabelClass(temp_json)
            # 注册
            self._register('inserter', temp_json['attributes']['class'], temp_json['inserter'])
            self._register('item', temp_json['attributes']['class'], temp_json['item'])
            # add_txt的下拉框里也要添加
            self.combo_box.addItem(temp_json['attributes']['class'])
            self.items.append(temp_json['attributes']['class'])
            cf.LABELS.append(temp_json)

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

    # 删除所有的item
    def remove_all_item(self):
        self._class_shortcuts.clear()
        self._class_context.clear()
        self._class_action.clear()
        self._class_config.clear()
        self.combo_box.clear()
        self.items.clear()
        temp_dict = copy.copy(self._class_buttons)
        for k, v in temp_dict.items():
            self._classbox_layout.removeWidget(v)
            # 下面这句很重要，不然相当于没删
            self._class_buttons[k].deleteLater()
        self._class_buttons.clear()
        cf.LABELS.clear()

        self._parea.setGeometry(0, 0, 200, 60)

    # 删除标签
    def remove_item(self, label_class):
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
                                self.items.pop(i)
                                break
                        self._class_buttons.pop(label_class)
                        break

                with open(label_path, 'w') as f:
                    json5.dump(temp, f, indent=4, separators=(',', ': '), sort_keys=True, ensure_ascii=False)
                self._parea.setGeometry(0, 0, 200, max(self._parea.geometry().height() - 40, 60))
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
        button = QPushButton(button_text)
        button.setCheckable(True)
        button.setFlat(True)
        button.clicked.connect(bind(self.onClassButtonPressed, label_class))
        self._class_buttons[label_class] = button
        self._parea.setGeometry(0, 0, 200, self._parea.geometry().height() + 40)
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
        # self._layout.insertWidget(1, self._label_editor, 0)
        self.insertionModeStarted.emit(label_class)

    def endInsertionMode(self, uncheck_buttons=True):
        if self._label_editor is not None:
            LOG.debug("Ending insertion/edit mode")
            self._label_editor.hide()
            # self._layout.removeWidget(self._label_editor)
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

    # 选择图片
    def select_image(self):
        image_types = ['*.jpg', '*.bmp', '*.png', '*.pgm', '*.ppm', '*.tiff', '*.tif', '*.gif']
        format_str = ' '.join(image_types)
        fname = QFileDialog.getOpenFileName(self, "select training source", '.',
                                            "Media files (%s)" % (format_str,))
        if fname is None or fname == '':
            return
        self.image_path = os.path.abspath(fname)
        self._image_label.setText(os.path.basename(self.image_path))

    # 获得图片路径对应的json路径
    def image2json(self, path):
        temp = path.split('.')
        return ''.join(temp[:-1]) + '.json'

    # 获得图片路径转成的训练图片路径
    def image2cpimage(self, path, id, length):
        length = max(length, 5)
        temp = path.split('.')
        return ''.join(temp[:-1]) + str(id).zfill(length) + '.' + temp[-1]

    # 判断是否包含瑕疵
    def contains_defect(self, annotations, defect_type):
        defects = set()
        for annotation in annotations:
            if 'class' in annotation:
                defects.add(annotation['class'])
        return defect_type.issubset(defects)

    # 生成训练数据
    def generate(self):
        # a = trainDialog(self.items, self)
        # a.exec_()
        a = TrainDialog(self)
        a.exec_()

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
        global brush2idx
        brush_idx = str(brush2idx[self.brush_combo_box.currentText()])
        temp_json = {'attributes': attributes, 'inserter': attributes_inserter,
                     'item': attributes_item,
                     'color': ','.join(map(str, self.color_info)),
                     'brush': brush_idx,
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
            self.items.append(temp_json['attributes']['class'])
            cf.LABELS.append(temp_json)
            # 写回json
            self.rewrite_json(temp_json)
        except Exception as e:
            print(e)

    # 颜色对话框
    def color_dialog(self):
        col = QtGui.QColorDialog.getColor()
        if col.isValid():
            self.color_label.setStyleSheet("QWidget { background-color: %s }"
                                           % col.name())
        self.color_info = col.getRgb()[:-1]

    # 设置控件的隐藏状态
    def component_visible(self, component_name, state):
        if component_name == '添加标签':
            self._group_box_add_label.setVisible(state)
        elif component_name == 'add_txt':
            self._group_box_add_txt.setVisible(state)
        elif component_name == 'add_files':
            self._group_box_add_files.setVisible(state)

    def _setupGUI(self):
        self._class_buttons = {}
        self._class_shortcuts = {}
        self._class_context = {}
        self._class_action = {}
        self._label_editor = None

        # Label class buttons
        self._parea = QGroupBox("Labels")
        self._classbox = QScrollArea()
        self._classbox_layout = FloatingLayout()
        self._parea.setLayout(self._classbox_layout)
        self._parea.setGeometry(0, 0, 200, 200)
        self._classbox.setWidget(self._parea)
        self._classbox.setGeometry(0, 0, 100, 100)
        # 添加txt模块
        self.combo_box = QComboBox()
        self._group_box_add_txt = QGroupBox('add_txt', self)
        self._group_box_add_txt_layout = QVBoxLayout()
        self._group_box_add_txt.setLayout(self._group_box_add_txt_layout)
        temp = cf.LABELS
        self.items = []
        # 获取所有的标签
        for i in temp:
            self.items.append(i['attributes']['class'])
        # 假如下拉框
        self.combo_box.addItems(self.items)
        self.add_txt_btn = QPushButton('add txt')
        self.add_txt_btn.clicked.connect(self.add_txt)
        # 加入下拉框和按钮
        self._group_box_add_txt_layout.addWidget(self.combo_box, 0)
        self._group_box_add_txt_layout.addWidget(self.add_txt_btn, 1)

        # 根据关键字搜索图片模块
        self._group_box_add_files = QGroupBox('add files', self)
        # 文件名包含的
        self._key_word = QLineEdit('')
        self._key_word.setPlaceholderText('merge')
        # 文件类型
        self._extension = QLineEdit('')
        self._extension.setPlaceholderText('bmp')
        self._search_btn = QPushButton('search files')
        self._group_box_add_files_layout = QVBoxLayout()
        # 加入控件
        self._group_box_add_files_layout.addWidget(self._key_word, 0)
        self._group_box_add_files_layout.addWidget(self._extension, 1)
        self._group_box_add_files_layout.addWidget(self._search_btn, 2)
        self._group_box_add_files.setLayout(self._group_box_add_files_layout)

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
        # 颜色
        color = QtGui.QColor(0, 0, 0)
        self.color_label = QtGui.QWidget()
        self.color_label.setStyleSheet("QWidget { background-color: %s }"
                                       % color.name())
        self.color_info = [0, 0, 0]
        self.color_layout = QtGui.QHBoxLayout()
        self.color_btn = QPushButton('选择颜色')
        self.color_btn.clicked.connect(self.color_dialog)
        self.color_layout.addWidget(self.color_label)
        self.color_layout.addWidget(self.color_btn)
        # 笔刷
        global brush2idx
        self.brush_combo_box = QComboBox()
        self.brush_combo_box.addItems(list(brush2idx.keys()))
        # 按钮
        self.attributes_add_btn = QPushButton('添加标签')
        self.attributes_add_btn.clicked.connect(self.add_attributes)
        # 加入控件
        self._add_label_group_layout.addWidget(self.attributes_LineEdit, 0)
        self._add_label_group_layout.addWidget(self.attributes_type, 1)
        self._add_label_group_layout.addWidget(self.hotkey, 2)
        self._add_label_group_layout.addWidget(self.text_LineEdit, 3)
        self._label_widget = QWidget()
        self._label_widget.setLayout(self.color_layout)
        self._add_label_group_layout.addWidget(self._label_widget, 4)
        self._add_label_group_layout.addWidget(self.brush_combo_box, 5)
        self._add_label_group_layout.addWidget(self.attributes_add_btn, 6)

        # 生成训练数据按钮
        self._file_button = QPushButton('生成训练数据')
        self._file_button.clicked.connect(self.generate)

        # Global widget
        self._layout = MyVBoxLayout()
        self.setLayout(self._layout)
        self._layout.addWidget(self._classbox, 1)
        self._layout.insertWidget(-1, self._group_box_add_label, 1)
        self._layout.insertWidget(-1, self._group_box_add_txt, 1)
        self._layout.insertWidget(-1, self._group_box_add_files, 1)
        self._layout.insertWidget(-1, self._file_button, 1)
