#!/usr/bin/env python
# _*_ coding:utf-8 _*_
import json
import fnmatch
import functools
import logging
import os
import sys
import shutil

import PyQt4.uic as uic
import json5
import sloth.Main as Main
from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import QSettings, QSize, QPoint, QVariant, QFileInfo, QTimer, pyqtSignal, QObject, Qt
from PyQt4.QtGui import (QMainWindow, QSizePolicy, QWidget, QVBoxLayout, QAction,
                         QKeySequence, QLabel, QItemSelectionModel, QMessageBox, QFileDialog, QFrame,
                         QDockWidget, QProgressBar, QProgressDialog, QCursor, QGraphicsPolygonItem, QDialog, QSpinBox,
                         QPushButton,
                         QRadioButton, QButtonGroup)
from sloth import APP_NAME
from sloth.annotations.container import AnnotationContainerFactory
from sloth.annotations.model import (AnnotationTreeView, FrameModelItem, ImageFileModelItem, CopyAnnotations,
                                     InterpolateRange)
from sloth.conf import config
from sloth.core.utils import import_callable
from sloth.items import inserters
from sloth.gui import qrc_icons  # needed for toolbar icons
from sloth.gui.annotationscene import AnnotationScene
from sloth.gui.controlbuttons import ControlButtonWidget
from sloth.gui.frameviewer import GraphicsView
from sloth.gui.propertyeditor import PropertyEditor
from sloth.utils.bind import bind, compose_noargs
import sloth.conf.default_config as cf
from PIL import Image
from PyQt4.QtGui import QDesktopServices
from PyQt4.QtCore import QUrl

Image.MAX_IMAGE_PIXELS = 1000000000

GUIDIR = os.path.join(os.path.dirname(__file__))

LOG = logging.getLogger(__name__)


class BackgroundLoader(QObject):
    finished = pyqtSignal()

    def __init__(self, model, status_bar, progress):
        QObject.__init__(self)
        self._max_levels = 3
        self._model = model
        self._status_bar = status_bar
        self._message_displayed = False
        self._progress = progress
        self._progress.setMinimum(0)
        self._progress.setMaximum(1000 * self._max_levels)
        self._progress.setMaximumWidth(150)

        self._level = 1
        self._iterator = self._model.iterator(maxlevels=self._level)
        self._pos = 0
        self._rows = self._model.root().rowCount() + 1
        self._next_rows = 0

        self.searched_file = None

    def load(self):
        if not self._message_displayed:
            self._status_bar.showMessage("Loading annotations...", 5000)
            self._message_displayed = True
        if self._level <= self._max_levels and self._rows > 0:
            try:
                item = next(self._iterator)
                self._next_rows += item.rowCount()
                self._pos += 1
                self._progress.setValue(int((float(self._pos) / float(self._rows) + self._level - 1) * 1000))
            except StopIteration:
                self._level += 1
                self._iterator = self._model.iterator(maxlevels=self._level)
                self._pos = 0
                self._rows = self._next_rows
                self._next_rows = 1
        else:
            LOG.debug("Loading finished...")
            self.finished.emit()


# 分裂对话框
class SplitDialog(QDialog):
    def __init__(self, func, parent=None):
        super(SplitDialog, self).__init__(parent)
        self.setupUi()
        self.spin_box_func = func

    # 关闭事件
    def closeEvent(self, event):
        reply = QtGui.QMessageBox.question(self,
                                           "确认",
                                           "确定好了吗",
                                           QtGui.QMessageBox.Yes | QtGui.QMessageBox.No | QtGui.QMessageBox.Cancel)
        if QtGui.QMessageBox.Yes == reply:
            print(self.spin_box.value())
            self.spin_box_func(self.spin_box.value(), self.vertical_button.isChecked())
        elif QtGui.QMessageBox.No == reply:
            self.spin_box_func(0)
        else:
            event.ignore()

    def setupUi(self):
        self.setWindowTitle('选择几等分')

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # n等分
        self.spin_box = QSpinBox()
        self.spin_box.setMinimum(1)
        self.spin_box.setValue(5)

        self.button_box = QButtonGroup()
        self.vertical_button = QRadioButton('垂直')
        self.horizontal_button = QRadioButton('水平')
        self.horizontal_button.setChecked(True)
        self.button_box.addButton(self.vertical_button)
        self.button_box.addButton(self.horizontal_button)

        # 确认按钮
        self.confirm_btn = QPushButton('确定')
        self.confirm_btn.clicked.connect(self.close)

        self.layout.addWidget(self.spin_box)
        self.layout.addWidget(self.vertical_button)
        self.layout.addWidget(self.horizontal_button)
        self.layout.addWidget(self.confirm_btn)


class MainWindow(QMainWindow):
    def __init__(self, labeltool, parent=None):
        QMainWindow.__init__(self, parent)

        self.idletimer = QTimer()
        self.loader = None

        self.labeltool = labeltool
        self.setupGui()
        self.loadApplicationSettings()
        self.onAnnotationsLoaded()

        self._item_dir = {}
        self.labeltool.set_to_image(self.to_image)
        self.labeltool.setGetState(self.is_test_mode)
        self.listenMouse = False

    def is_test_mode(self):
        return self.mode.text()

    # Slots
    def onPluginLoaded(self, action):
        self.ui.menuPlugins.addAction(action)

    def onStatusMessage(self, message=''):
        self.statusBar().showMessage(message, 5000)

    def onModelDirtyChanged(self, dirty):
        postfix = "[+]" if dirty else ""
        if self.labeltool.getCurrentFilename() is not None:
            self.setWindowTitle("%s - %s %s" % \
                                (APP_NAME, QFileInfo(self.labeltool.getCurrentFilename()).fileName(), postfix))
        else:
            self.setWindowTitle("%s - Unnamed %s" % (APP_NAME, postfix))

    def onMousePositionChanged(self, x, y):
        self.posinfo.setText("%d, %d" % (x, y))

    def startBackgroundLoading(self):
        self.stopBackgroundLoading(forced=True)
        self.loader = BackgroundLoader(self.labeltool.model(), self.statusBar(), self.sb_progress)
        self.idletimer.timeout.connect(self.loader.load)
        self.loader.finished.connect(self.stopBackgroundLoading)
        self.statusBar().addWidget(self.sb_progress)
        self.sb_progress.show()
        self.idletimer.start()

    def stopBackgroundLoading(self, forced=False):
        if not forced:
            self.statusBar().showMessage("Background loading finished", 5000)
        self.idletimer.stop()
        if self.loader is not None:
            self.idletimer.timeout.disconnect(self.loader.load)
            self.statusBar().removeWidget(self.sb_progress)
            self.loader = None

    def onAnnotationsLoaded(self):
        self.labeltool.model().dirtyChanged.connect(self.onModelDirtyChanged)
        self.onModelDirtyChanged(self.labeltool.model().dirty())
        self.treeview.setModel(self.labeltool.model())
        self.scene.setModel(self.labeltool.model())
        self.selectionmodel = QItemSelectionModel(self.labeltool.model())
        self.treeview.setSelectionModel(self.selectionmodel)
        self.treeview.selectionModel().currentChanged.connect(self.labeltool.setCurrentImage)
        self.property_editor.onModelChanged(self.labeltool.model())
        self.startBackgroundLoading()

    # 图片切换了之后触发
    def onCurrentImageChanged(self):
        new_image = self.labeltool.currentImage()
        self.scene.setCurrentImage(new_image)
        self.onFitToWindowModeChanged()
        self.treeview.scrollTo(new_image.index())

        img = self.labeltool.getImage(new_image)
        if img is None:
            QMessageBox.warning(self, "Warning",
                                '图片找不到了，请查看是否从软件外部直接删除图片\n并考虑重新加载图片以正常标定',
                                QMessageBox.Ok)
            return
        if img.any() is None:
            self.controls.setFilename("")
            self.selectionmodel.setCurrentIndex(new_image.index(),
                                                QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
            return
        h = img.shape[0]
        w = img.shape[1]
        self.image_resolution.setText("%dx%d" % (w, h))

        # TODO: This info should be obtained from AnnotationModel or LabelTool
        if isinstance(new_image, FrameModelItem):
            self.controls.setFrameNumAndTimestamp(new_image.framenum(), new_image.timestamp())
        elif isinstance(new_image, ImageFileModelItem):
            self.controls.setFilename(os.path.basename(new_image['filename']))

        self.selectionmodel.setCurrentIndex(new_image.index(),
                                            QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)

    def onFitToWindowModeChanged(self):
        if self.options["Fit-to-window mode"].isChecked():
            self.view.fitInView()

    def onEnumerateCornersModeChanged(self):
        if self.options["Enumerate-corners mode"].isChecked():
            self.scene.enumerateCorners()
            self.onCurrentImageChanged()
        else:
            self.scene.removeCorners()
            self.onCurrentImageChanged()

    def onCopyAnnotationsModeChanged(self):
        if self.annotationMenu["Copy from previous"].isChecked():
            self.copyAnnotations.copy()
            self.annotationMenu["Copy from previous"].setChecked(False)

    def onInterpolateRangeModeChanged(self):
        if self.annotationMenu["Interpolate range"].isChecked():
            self.interpolateRange.interpolateRange()
            self.annotationMenu["Interpolate range"].setChecked(False)

    def onScaleChanged(self, scale):
        self.zoominfo.setText("%.2f%%" % (100 * scale,))

    def initShortcuts(self, HOTKEYS):
        self.shortcuts = []

        for hotkey in HOTKEYS:
            assert len(hotkey) >= 2
            key = hotkey[0]
            fun = hotkey[1]
            desc = ""
            if len(hotkey) > 2:
                desc = hotkey[2]
            if type(fun) == str:
                fun = import_callable(fun)

            hk = QAction(desc, self)
            hk.setShortcut(QKeySequence(key))
            hk.setEnabled(True)
            if hasattr(fun, '__call__'):
                hk.triggered.connect(bind(fun, self.labeltool))
            else:
                hk.triggered.connect(compose_noargs([bind(f, self.labeltool) for f in fun]))
            self.ui.menuShortcuts.addAction(hk)
            self.shortcuts.append(hk)

    def initOptions(self):
        self.options = {}
        for o in ["Fit-to-window mode"]:
            action = QAction(o, self)
            action.setCheckable(True)
            self.ui.menuOptions.addAction(action)
            self.options[o] = action

        for o in ["Enumerate-corners mode"]:
            action = QAction(o, self)
            action.setCheckable(True)
            self.ui.menuOptions.addAction(action)
            self.options[o] = action

    def initAnnotationMenu(self):
        self.annotationMenu = {}
        for a in ["Copy from previous"]:
            action = QAction(a, self)
            action.setCheckable(True)
            self.ui.menuAnnotation.addAction(action)
            self.annotationMenu[a] = action

        for a in ["Interpolate range"]:
            action = QAction(a, self)
            action.setCheckable(True)
            self.ui.menuAnnotation.addAction(action)
            self.annotationMenu[a] = action

    # 获得到image级别
    def to_image(self):
        temp = self.treeview.currentIndex()
        while temp.parent().data() is not None:
            temp = temp.parent()
        return temp

    # 设置右键的菜单位置
    # def showContextMenu(self):
    #     """
    #     设置右键的菜单位置
    #     """
    #     self.contextMenu.exec_(QCursor.pos())

    # 打开图片所在路径
    def open_image_directory(self):
        """
        打开图片所在路径
        """
        a = self.to_image()
        # while a.parent
        annotations = self.labeltool.annotations()
        if a.row() < 0:
            return
        open_path = os.path.dirname(annotations[a.row()]['filename'])
        try:
            QDesktopServices.openUrl(QUrl(open_path))
        except Exception as e:
            print(e)

    # 加载图片的时候顺便加载json
    def get_pictures_with_json(self, pictures_path, key_word='merge', extension=None):
        """
        加载图片的时候顺便加载json
        :param pictures_path: 图片的文件夹
        :param key_word: 标志位
        :param extension: 扩展名
        :return: json
        """
        json_picture = []
        for root, dirs, files in os.walk(pictures_path):
            for file in files:
                file_name, ext = os.path.splitext(file)
                if key_word is None or key_word is '' or file_name.find(key_word) >= 0:
                    if extension is None or ext.lower() == '.' + extension:
                        # 获得绝对路径
                        filename = os.path.join(root, file)
                        # 获得相对路径
                        filename = self.real_path(filename, '.')
                        temp_json = {"annotations": [], "class": "image", "filename": filename}
                        try:
                            # 对应的json路径
                            json_path = os.path.join(root, file_name + '.json')
                            flag = True
                            if not os.path.exists(json_path):
                                json_path = os.path.join(os.path.join(root, 'test_images'), file_name + '.json')
                                flag = False
                            if os.path.exists(json_path):
                                with open(json_path, 'r') as f:
                                    json_array = json.load(f)
                                    for json_object in json_array:
                                        if flag and json_object['filename'].startswith('..'):
                                            continue
                                        temp_json['annotations'] = json_object['annotations']
                                        break
                        except Exception as e:
                            print(e)
                        finally:
                            json_picture.append(temp_json)
        return json_picture

    # 搜索文件
    def search_file(self):
        self.searched_file = None
        key_word = self.property_editor.get_key_word()
        extension = self.property_editor.get_extension().lower()
        if extension == 'json':
            self.add_all_json(key_word)
        else:
            temp_directory = r'.'
            if not os.path.exists(temp_directory):
                temp_directory = ''
            directory = QFileDialog.getExistingDirectory(self, directory=temp_directory)
            if directory is None or '' == directory or not os.path.exists(directory):
                return
            if self.mode.text() == '测试标定模式':
                test_image = os.path.join(directory, 'test_Images')
                if not os.path.exists(test_image):
                    os.mkdir(test_image)
            fnames = self.get_pictures_with_json(directory, key_word, extension)
            numFiles = len(fnames)
            if numFiles <= 0:
                return
            else:
                self.searched_file = directory
                # 临时json
                temp_json_path = self.get_name()
                # 保存json
                container = AnnotationContainerFactory(config.CONTAINERS).create(temp_json_path)
                container.save(fnames, temp_json_path)
                # 读入json
                self.labeltool.loadAnnotations(temp_json_path)
                # 删除临时的json
                os.remove(temp_json_path)
                # temp_json = self.get_name()
                # with open(temp_json, 'w') as f:
                #     json5.dump(fnames, f)
                # self.labeltool.loadAnnotations(temp_json)
                # os.remove(temp_json)

    # 改变部件可视
    def change_visible(self, action):
        state = action.isChecked()
        self.property_editor.component_visible(action.text(), not state)

    # 删除treeview 中所有的
    def remove_all_treeview_item(self):
        try:
            if self.searched_file is None:
                return
            if not os.path.exists(self.searched_file):
                QMessageBox.warning(self, "Warning",
                                    '不存在要删除的文件夹',
                                    QMessageBox.Ok)
                return
            result = QMessageBox.warning(self, 'Warning', '是否删除 %s 中的所有文件' % self.searched_file,
                                         QMessageBox.Ok | QMessageBox.Cancel)
            if QMessageBox.Cancel == result:
                return
            # 临时存json
            temp_save = self.get_name()
            # 存储json
            with open(temp_save, 'w') as f:
                json5.dump([], f)
            self.labeltool.loadAnnotations(temp_save)
            # 删除临时的json
            os.remove(temp_save)
            shutil.rmtree(self.searched_file)
            self.searched_file = None
        except WindowsError as e:
            if 13 == e.errno:
                error_msg = '另一个程序正在使用此文件，进程无法访问。: %s\n考虑关闭相应文件后再次删除' % e.filename
            elif 5 == e.errno:
                error_msg = '无权限删除该文件夹: %s' % e.filename
            elif 2 == e.errno:
                error_msg = '不存在要删除的文件夹: %s' % e.filename
            elif 41 == e.errno:
                error_msg = '目录不是空的。: %s考虑手动删除目录' % e.filename
            else:
                error_msg = '系统错误'
            print(e)
            print(e.errno)
            print(e.filename)
            QMessageBox.warning(self, "Warning",
                                error_msg,
                                QMessageBox.Ok)
        except Exception as e:
            print(e)
            QMessageBox.warning(self, "Warning",
                                '未知错误',
                                QMessageBox.Ok)

    # 删除treeview 中的
    def remove_treeview_Item(self):
        try:
            t = self.to_image()
            if t.row() < 0:
                return
            annotations = self.labeltool.annotations()
            delete_file_dir = os.path.dirname(annotations[t.row()]['filename'])
            delete_file_dir = os.path.join(delete_file_dir, '..')
            # 删除的文件夹
            delete_file_dir = QFileDialog.getExistingDirectory(self, caption='请选择要删除的文件夹',
                                                               directory=delete_file_dir)
            if delete_file_dir is None or '' == delete_file_dir or not os.path.exists(delete_file_dir):
                return

            result = QMessageBox.warning(self, 'Warning', '是否删除 %s 中的所有文件' % delete_file_dir,
                                         QMessageBox.Ok | QMessageBox.Cancel)
            if QMessageBox.Cancel == result:
                return
            temp_annotations = []
            # 如果图片所在文件夹以删除的文件夹开头（子目录），则删除
            for annotation in annotations:
                if not os.path.dirname(annotation['filename']).startswith(delete_file_dir):
                    temp_annotations.append(annotation)
            # 临时存json
            temp_save = self.get_name()
            container = AnnotationContainerFactory(config.CONTAINERS).create(temp_save)
            container.save(temp_annotations, temp_save)
            self.labeltool.loadAnnotations(temp_save)
            # 删除临时的json
            os.remove(temp_save)
            # 递归删除文件夹
            shutil.rmtree(delete_file_dir)
        except WindowsError as e:
            if 13 == e.errno:
                error_msg = '另一个程序正在使用此文件，进程无法访问。: %s\n如果图片已经删除，考虑自行删除文件夹' % e.filename
            elif 5 == e.errno:
                error_msg = '无权限删除该文件夹: %s' % e.filename
            elif 2 == e.errno:
                error_msg = '不存在要删除的文件夹: %s' % e.filename
            elif 41 == e.errno:
                error_msg = '目录不是空的。: %s\n考虑手动删除目录' % e.filename
            else:
                error_msg = '系统错误'
            print(e)
            print(e.errno)
            print(e.filename)
            QMessageBox.warning(self, "Warning",
                                error_msg,
                                QMessageBox.Ok)

        except Exception as e:
            print(e)
            QMessageBox.warning(self, "Warning",
                                '未知错误',
                                QMessageBox.Ok)

    # 获得分裂对话框的spin_box和分裂方式
    def set_num(self, num, vertical):
        self.split_num = num
        self.vertical = vertical

    # 将矩形n等分
    def split_rectangle(self):
        """
        将矩形n等分
        """

        temp = self.treeview.currentIndex()
        # 右键的是图片级别
        if temp.parent().data() is None:
            print('已经是图片级别了')
            return

        self.split_num = 0

        # 获得标签级别
        while not (temp.parent().data() is not None and temp.parent().parent().data() is None):
            temp = temp.parent()
            break
        attribute_class = temp.data()
        config = Main.get_json()
        item_type = None
        for current_json in config:
            if current_json['attributes']['class'] == attribute_class:
                item_type = current_json['item']
                break
        data = None
        for item in self.scene.selectedItems():
            if item_type == 'sloth.items.RectItem':
                data = item._rect
                break
        if data is None:
            return
        split_dialog = SplitDialog(self.set_num, self)
        split_dialog.exec_()

        if self.split_num <= 0:
            return
        self.scene.deleteSelectedItems()
        if item_type == 'sloth.items.RectItem':
            rect = data
            height = rect.height()
            width = rect.width()
            height_increse = 0
            width_increase = 0
            if self.vertical:
                height /= self.split_num
                height_increse = height
            else:
                width /= self.split_num
                width_increase = width
            for idx in range(self.split_num):
                self.property_editor._class_buttons[attribute_class].click()
                inserter = self.scene._inserter
                inserter._ann['class'] = attribute_class
                inserter._ann[None] = None
                inserter._ann.update({inserter._prefix + 'x': rect.x() + width_increase * idx,
                                      inserter._prefix + 'y': rect.y() + height_increse * idx,
                                      inserter._prefix + 'width': width,
                                      inserter._prefix + 'height': height})
                inserter._ann.update(inserter._default_properties)
                if inserter._commit:
                    self.scene._image_item.addAnnotation(inserter._ann)
                inserter.annotationFinished.emit()
                inserter._init_pos = None
                inserter._aiming = True
                inserter.annotationFinished.emit()
                self.scene.views()[0].viewport().setCursor(Qt.CrossCursor)
                self.property_editor._class_buttons[attribute_class].click()
            i = 0
            last_child = None
            father = temp.parent()
            while True:
                child = father.child(i, 0)
                if child.data() is None:
                    break
                last_child = child
                i += 1
            if last_child is None:
                return
            self.treeview.setCurrentIndex(last_child)
        else:
            return

    # 初始化界面
    def setupGui(self):
        self.ui = uic.loadUi(os.path.join(GUIDIR, "labeltool.ui"), self)
        # get inserters and items from labels
        # FIXME for handling the new-style config correctly
        inserters = dict([(label['attributes']['class'], label['inserter'])
                          for label in config.LABELS
                          if 'class' in label.get('attributes', {}) and 'inserter' in label])
        items = dict([(label['attributes']['class'], label['item'])
                      for label in config.LABELS
                      if 'class' in label.get('attributes', {}) and 'item' in label])

        # Property Editor
        self.property_editor = PropertyEditor(config.LABELS)
        self.property_editor.setFunction(self.search_file)
        t = QtGui.QScrollArea()
        t.setWidget(self.property_editor)
        self.ui.dockProperties.setWidget(t)
        # Scene
        self.scene = AnnotationScene(self.labeltool, self.property_editor, items=items, inserters=inserters)
        self.property_editor.insertionModeStarted.connect(self.scene.onInsertionModeStarted)
        self.property_editor.insertionModeEnded.connect(self.scene.onInsertionModeEnded)

        self.property_editor._register = self.scene.add_label

        # SceneView
        self.view = GraphicsView(self)

        # 在图片上设置右键菜单
        # self.contextMenu = QtGui.QMenu(self)
        # self.actionA = self.contextMenu.addAction('打开文件所在文件夹')
        # self.actionA.triggered.connect(self.open_image_directory)
        # self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # self.view.customContextMenuRequested.connect(self.showContextMenu)
        self.view.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        self.view.setScene(self.scene)

        self.central_widget = QWidget()
        self.central_layout = QVBoxLayout()
        self.controls = ControlButtonWidget()
        # give functions as lambdas, or else they will be called with a bool as parameter
        self.controls.back_button.clicked.connect(lambda lt: self.labeltool.gotoPrevious())
        self.controls.forward_button.clicked.connect(lambda lt: self.labeltool.gotoNext())

        self.central_layout.addWidget(self.controls)
        self.central_layout.addWidget(self.view)
        self.central_widget.setLayout(self.central_layout)
        self.setCentralWidget(self.central_widget)

        self.initShortcuts(config.HOTKEYS)
        self.initOptions()
        self.initAnnotationMenu()

        self.treeview = AnnotationTreeView()
        # 在treeview设置右键
        self.treeview.set_openDirectory(self.open_image_directory, self.remove_treeview_Item, self.split_rectangle)
        self.treeview.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        self.ui.dockAnnotations.setWidget(self.treeview)

        self.scene.selectionChanged.connect(self.scene.onSelectionChanged)
        self.treeview.selectedItemsChanged.connect(self.scene.onSelectionChangedInTreeView)

        self.posinfo = QLabel("-1, -1")
        self.posinfo.setFrameStyle(QFrame.StyledPanel)
        self.statusBar().addPermanentWidget(self.posinfo)
        self.scene.mousePositionChanged.connect(self.onMousePositionChanged)
        self.scene.mousePress.connect(self.onMousePress)
        self.scene.mouseRelease.connect(self.onMouseRelease)
        self.image_resolution = QLabel("[no image]")
        self.image_resolution.setFrameStyle(QFrame.StyledPanel)
        self.statusBar().addPermanentWidget(self.image_resolution)

        self.zoominfo = QLabel()
        self.zoominfo.setFrameStyle(QFrame.StyledPanel)
        self.statusBar().addPermanentWidget(self.zoominfo)
        self.view.scaleChanged.connect(self.onScaleChanged)
        self.onScaleChanged(self.view.getScale())

        self.sb_progress = QProgressBar()

        # View menu
        self.ui.menu_Views.addAction(self.ui.dockProperties.toggleViewAction())
        self.ui.menu_Views.addAction(self.ui.dockAnnotations.toggleViewAction())
        self.ui.actionAdd_label.triggered.connect(bind(self.change_visible, self.ui.actionAdd_label))
        self.ui.actionAdd_txt.triggered.connect(bind(self.change_visible, self.ui.actionAdd_txt))
        self.ui.actionAdd_files.triggered.connect(bind(self.change_visible, self.ui.actionAdd_files))

        # Annotation menu
        self.copyAnnotations = CopyAnnotations(self.labeltool)
        self.interpolateRange = InterpolateRange(self.labeltool)

        # Show the UI.  It is important that this comes *after* the above
        # adding of custom widgets, especially the central widget.  Otherwise the
        # dock widgets would be far to large.
        self.ui.show()

        ## connect action signals
        self.connectActions()

        self.mode = self.ui.toolBar.addAction('训练标定模式', self.change_mode)
        self.save_all_mode = self.ui.toolBar.addAction('只保存当前的', self.save_change_mode)
        self.save_all_mode.setVisible(False)
        # 删除所有的
        self.ui.actionDelete_all.triggered.connect(self.remove_all_treeview_item)

    # 切换模式
    def change_mode(self):
        """
        训练标定模式与测试标定模式互相转换
        """
        if self.mode.text() == '训练标定模式':
            self.mode.setText('测试标定模式')
            self.save_all_mode.setVisible(True)
        else:
            self.mode.setText('训练标定模式')
            self.save_all_mode.setVisible(False)

    # 切换保存模式
    def save_change_mode(self):
        """
        只保存当前的图片模式和保存全部图片模式互相转换
        """
        if self.save_all_mode.text() == '只保存当前的':
            self.save_all_mode.setText('保存全部图片')
        else:
            self.save_all_mode.setText('只保存当前的')

    # 判断图片json的合法性
    def judge_picture_json(self, json_array):
        """
        判断图片json_array的合法性
        :param json_array:
        :return: 返回json_array中合格的地方
        """
        # TODO 判断图片的json的合法性
        pass

    # 获得临时json的名字
    def get_name(self, temp_json_path='faQ.json'):
        """
        获得临时json的名字
        :param temp_json_path:json的初始名字
        :return: json的名字
        """
        while os.path.exists(temp_json_path):
            temp_json_path = os.path.splitext(temp_json_path)[0] + '(1)' + '.json'
        return temp_json_path

    # path和项目同盘符则返回相对start路径，否则返回绝对路径
    def real_path(self, path, start):
        """
        如果path和项目同盘符则返回相对start路径，否则返回绝对路径
        :param path: 路径
        :param start: 相对的路径
        :return: 路径
        """
        if os.path.isabs(path):
            return path
        return os.path.relpath(path, start)

    # 添加json
    def add_json(self):
        temp_json = []
        # 文件set，每个文件只读一次
        filename_set = set()
        path = '.'
        # 获取临时json路径
        temp_json_path = self.get_name()
        # 保存json
        self.labeltool.saveAnnotations(temp_json_path)
        # 读入json
        with open(temp_json_path, 'r') as f:
            json_array = json.load(f)
        for i in range(len(json_array)):
            current_json = json_array[i]
            if 'filename' in current_json:
                # 绝对路径
                filename = os.path.abspath(os.path.join('.', current_json['filename']))
                # 相对路径
                filename = self.real_path(filename, '.')
                # 只读一次
                if filename in filename_set:
                    continue
                else:
                    filename_set.add(filename)
                current_json['filename'] = filename
                # 假如json
                temp_json.append(current_json)
        # 删除临时json
        os.remove(temp_json_path)
        json_types = ['*.json']
        format_str = ' '.join(json_types)
        # 读取多个json
        fnames = QFileDialog.getOpenFileNames(self, "%s - Add json File" % APP_NAME, path,
                                              "json files (%s)" % (format_str,))
        for json_file in fnames:
            with open(json_file, 'r') as f:
                json_array = json.load(f)
            for i in range(len(json_array)):
                current_json = json_array[i]
                # 必须要有'annotations', 'class', 'filename'
                if 'filename' in current_json and \
                        set(current_json.keys()).issubset({'annotations', 'class', 'filename'}):
                    root = os.path.dirname(json_file)
                    # 绝对路径
                    filename = os.path.abspath(os.path.join(root, current_json['filename']))
                    # 相对路径
                    filename = self.real_path(filename, '.')
                    # 只加一次
                    if filename in filename_set:
                        continue
                    else:
                        filename_set.add(filename)
                    current_json['filename'] = filename
                    # 加入json
                    temp_json.append(current_json)
        # 获取json
        temp_json_path = self.get_name()
        container = AnnotationContainerFactory(config.CONTAINERS).create(temp_json_path)
        # 保存json
        container.save(temp_json, temp_json_path)
        # 读取json
        self.labeltool.loadAnnotations(temp_json_path)
        # 移除临时json
        os.remove(temp_json_path)

    # 添加所有的json
    def add_all_json(self, key_word=None):
        """
        添加所有的json
        :param key_word: json的关键字
        """
        temp_json = []
        # 文件set，保证文件只加一次
        filename_set = set()
        # 获取临时json路径
        temp_json_path = self.get_name()
        # 保存目前的json
        self.labeltool.saveAnnotations(temp_json_path)
        # 读入刚刚的json
        with open(temp_json_path, 'r') as f:
            temp = json.load(f)
        for i in range(len(temp)):
            current_json = temp[i]
            if 'filename' in current_json:
                # 绝对路径
                filename = os.path.abspath(os.path.join('.', current_json['filename']))
                # 相对路径
                filename = self.real_path(filename, '.')
                # 只添加一次
                if filename in filename_set:
                    continue
                else:
                    filename_set.add(filename)
                current_json['filename'] = filename
                temp_json.append(current_json)
        # 删除临时的json
        os.remove(temp_json_path)
        # 要读取的json文件夹
        json_path = QFileDialog.getExistingDirectory(self)
        if json_path is not None and '' != json_path and os.path.exists(json_path):
            self.searched_file = json_path
        readed_flag = False
        # 遍历所有的文件
        for root, dirs, files in os.walk(json_path):
            for file in files:
                # 获取文件名字
                temp_split = os.path.splitext(file)
                # 只读取json的
                if temp_split[-1] == '.json':
                    # 查看是否包含关键字key_word
                    if key_word is not None and key_word and temp_split[0].find(str(key_word)) < 0:
                        continue
                    # json的路径
                    json_file = os.path.join(root, file)
                    try:
                        with open(json_file, 'r') as f:
                            temp = json.load(f)
                        if not isinstance(temp, list):
                            raise Exception('jsonError')
                    except Exception as e:
                        print(e)
                        print('读取%s失败' % json_file)
                        continue
                    for i in range(len(temp)):
                        # 如果读进来是个json而不是json_array，将会报错
                        try:
                            current_json = temp[i]
                            # 判断filename在json中
                            if 'filename' in current_json and \
                                    set(current_json.keys()).issubset({'annotations', 'class', 'filename'}):
                                if not readed_flag:
                                    filename_set.clear()
                                    readed_flag = True
                                    temp_json.clear()
                                # 绝对路径
                                filename = os.path.abspath(os.path.join(root, current_json['filename']))
                                # 相对路径
                                filename = self.real_path(filename, '.')
                                # 只读取一次
                                if filename in filename_set:
                                    continue
                                else:
                                    filename_set.add(filename)
                                current_json['filename'] = filename
                                # 加入json
                                temp_json.append(current_json)
                        except Exception as e:
                            print(e)
                            break
        # 临时json
        temp_json_path = self.get_name()
        # 保存json
        container = AnnotationContainerFactory(config.CONTAINERS).create(temp_json_path)
        container.save(temp_json, temp_json_path)
        # 读入json
        self.labeltool.loadAnnotations(temp_json_path)
        # 删除临时的json
        os.remove(temp_json_path)

    # 按点多边形
    def undo_polygon(self, model_index):
        """
        撤回多边形，按照点撤回，如ABCDE->ABCD
        :param model_index: tree_view的index
        """
        if model_index.parent().data() is None:
            return
        # 判断有没有父亲的父亲
        if model_index.parent().parent().data() is not None:
            return
        attribute_class = model_index.data()
        temp_conf = cf.LABELS
        for current_json in temp_conf:
            # 获得类型
            temp_attribute_class = current_json['attributes']['class']
            # 获得类型
            temp_type = current_json["item"]
            if attribute_class == temp_attribute_class:
                # 多边形才有撤回功能
                if temp_type == "sloth.items.PolygonItem":
                    print('is PolygonItem')
                    break
                else:
                    return

        attribute_class = model_index.data()
        if attribute_class == '':
            return
        for i in self.scene.selectedItems():
            polygon = i._polygon
            if polygon.size() == 1:
                self.scene.deleteSelectedItems()
                return
            # 删除最后一个
            # polygon = polygon[0:-1]
            self.scene.deleteSelectedItems()
            self.scene.onInsertionModeStarted(attribute_class)
            inserter = self.scene._inserter
            inserter._ann['class'] = attribute_class
            inserter._ann[None] = None
            item = QGraphicsPolygonItem(polygon)
            item.setPen(inserter.pen())
            inserter._item = item
            self.scene.addItem(item)

    # 撤回
    def undo(self):
        """
        撤回
        """
        if self.listenMouse:
            return
        # a = self.to_image()
        a = self.labeltool.currentImage().index()
        i = 0
        last_child = None
        while True:
            child = a.child(i, 0)
            if child.data() is None:
                break
            last_child = child
            i += 1
        if last_child is None:
            return
        i = 0
        # data = []
        # while last_child.child(i, 1).data() is None:
        #     child = last_child.child(i, 1)
        #     data.append(child.data())
        #     i += 1
        annotations = self.labeltool.annotations()
        if a.row() < 0:
            return
        # 获得文件
        open_path = annotations[a.row()]['filename']
        # 给文件加撤回列表
        if open_path not in self._item_dir:
            self._item_dir[open_path] = []
        self.scene.deselectAllItems()
        self.treeview.setCurrentIndex(last_child)
        items = [self.treeview.model().itemFromIndex(index) for index in
                 self.treeview.selectionModel().selectedIndexes()]
        self.treeview.selectedItemsChanged.emit(items)
        # self.treeview.setSelectedItems(last_child)
        config = Main.get_json()
        item_type = None
        for current_json in config:
            if current_json['attributes']['class'] == last_child.data():
                item_type = current_json['item']
                break
        data = None
        for item in self.scene.selectedItems():
            if item_type == 'sloth.items.PointItem':
                data = item._point
                break
            elif item_type == 'sloth.items.RectItem':
                data = item._rect
                break
            elif item_type == 'sloth.items.PolygonItem':
                data = item._polygon
                break
        if data is None:
            return
        self._item_dir[open_path].append([last_child.data(), item_type, data])
        self.scene.deleteSelectedItems()
        # self.treeview.setCurrentIndex(a)

    # 重做
    def redo(self):
        """
        重做（相当于ctrl+y或者ctrl+shift+z)
        """
        if self.listenMouse:
            return
        a = self.labeltool.currentImage().index()
        annotations = self.labeltool.annotations()
        if a.row() < 0:
            self.treeview.setCurrentIndex(a)
            return
        open_path = annotations[a.row()]['filename']
        if open_path not in self._item_dir or len(self._item_dir[open_path]) == 0:
            return
        if len(self._item_dir[open_path]) == 0:
            return
        attribute_class = self._item_dir[open_path][-1][0]
        item_type = self._item_dir[open_path][-1][1]
        data = self._item_dir[open_path][-1][2]
        if attribute_class == '' or attribute_class is None:
            return
        if item_type is None:
            return
        self.property_editor._class_buttons[attribute_class].click()
        inserter = self.scene._inserter
        inserter._ann['class'] = attribute_class
        inserter._ann[None] = None
        if item_type == 'sloth.items.PointItem':
            inserter._ann.update({
                inserter._prefix + 'x': data.x(),
                inserter._prefix + 'y': data.y()})
            inserter._ann.update(inserter._default_properties)
            if inserter._commit:
                self.scene._image_item.addAnnotation(inserter._ann)
        elif item_type == 'sloth.items.RectItem':
            rect = data
            inserter._ann.update({inserter._prefix + 'x': rect.x(),
                                  inserter._prefix + 'y': rect.y(),
                                  inserter._prefix + 'width': rect.width(),
                                  inserter._prefix + 'height': rect.height()})
            inserter._ann.update(inserter._default_properties)
            if inserter._commit:
                self.scene._image_item.addAnnotation(inserter._ann)
            inserter.annotationFinished.emit()
            inserter._init_pos = None
            inserter._aiming = True
            self.scene.views()[0].viewport().setCursor(Qt.CrossCursor)
        elif item_type == 'sloth.items.PolygonItem':
            polygon = data
            inserter._item = QGraphicsPolygonItem(polygon)
            inserter._updateAnnotation()
            if inserter._commit:
                self.scene._image_item.addAnnotation(inserter._ann)
            inserter._item = None
        inserter.annotationFinished.emit()
        self.property_editor._class_buttons[attribute_class].click()
        if len(self._item_dir[open_path]) == 1:
            self._item_dir[open_path] = []
        else:
            self._item_dir[open_path] = self._item_dir[open_path][0:-1]

    # 切换配置文件
    def change_config(self):
        """
        更改当前的配置文件
        """
        path = '.'
        filename = self.labeltool.getCurrentFilename()
        if (filename is not None) and (len(filename) > 0):
            path = QFileInfo(filename).path()
        config_types = ['*.json']
        format_str = ' '.join(config_types)
        fname = QFileDialog.getOpenFileName(self, "%s - Add Media File" % APP_NAME, path,
                                            "Media files (%s)" % (format_str,))
        if fname is None or fname == '':
            return
        # 转绝对路径
        fname = os.path.abspath(fname)
        try:
            with open(fname, 'r') as f:
                configs = json5.load(f)
            if not Main.isConfig(configs):
                QMessageBox.warning(self, "Warning",
                                    '选择的配置文件错误或者为空，无法切换配置文件',
                                    QMessageBox.Ok)
                return
        except Exception as e:
            print(e)
            QMessageBox.warning(self, "Warning",
                                '选择的配置文件错误或者为空，无法切换配置文件',
                                QMessageBox.Ok)
            return
        # 移除原来的配置文件
        self.property_editor.remove_all_item()
        # 加入新的配置文件
        self.property_editor.addLabelClassByPath(fname)

    # 事件绑定
    def connectActions(self):
        """
        事件绑定
        """
        # File menu
        self.ui.actionNew.triggered.connect(self.fileNew)
        self.ui.actionOpen.triggered.connect(self.fileOpen)
        self.ui.actionSave.triggered.connect(self.fileSave)
        self.ui.actionSave_As.triggered.connect(self.fileSaveAs)
        self.ui.actionExit.triggered.connect(self.close)

        # View menu
        self.ui.actionLocked.toggled.connect(self.onViewsLockedChanged)

        # Help menu
        self.ui.action_About.triggered.connect(self.about)

        # Navigation
        self.ui.action_Add_Image.triggered.connect(self.addMediaFile)
        # self.ui.action_Add_All_Image.triggered.connect(self.addMediaFile1)
        self.ui.actionAdd_Json.triggered.connect(self.add_json)
        # self.ui.actionAdd_All_Json.triggered.connect(self.add_all_json)

        self.ui.actionChange_Config.triggered.connect(self.change_config)

        self.ui.actionNext.triggered.connect(self.labeltool.gotoNext)
        self.ui.actionPrevious.triggered.connect(self.labeltool.gotoPrevious)
        self.ui.actionZoom_In.triggered.connect(functools.partial(self.view.setScaleRelative, 1.2))
        self.ui.actionZoom_Out.triggered.connect(functools.partial(self.view.setScaleRelative, 1 / 1.2))
        self.ui.action_Undo.triggered.connect(self.undo)

        # Connections to LabelTool
        self.labeltool.pluginLoaded.connect(self.onPluginLoaded)
        self.labeltool.statusMessage.connect(self.onStatusMessage)
        self.labeltool.annotationsLoaded.connect(self.onAnnotationsLoaded)
        self.labeltool.currentImageChanged.connect(self.onCurrentImageChanged)

        # options menu
        self.options["Fit-to-window mode"].changed.connect(self.onFitToWindowModeChanged)
        self.options["Enumerate-corners mode"].changed.connect(self.onEnumerateCornersModeChanged)

        # annotation menu
        self.annotationMenu["Copy from previous"].changed.connect(self.onCopyAnnotationsModeChanged)
        self.annotationMenu["Interpolate range"].changed.connect(self.onInterpolateRangeModeChanged)

    def loadApplicationSettings(self):
        settings = QSettings()
        size = settings.value("MainWindow/Size", QSize(800, 600))
        pos = settings.value("MainWindow/Position", QPoint(10, 10))
        state = settings.value("MainWindow/State")
        locked = settings.value("MainWindow/ViewsLocked", False)
        if isinstance(size, QVariant): size = size.toSize()
        if isinstance(pos, QVariant): pos = pos.toPoint()
        if isinstance(state, QVariant): state = state.toByteArray()
        if isinstance(locked, QVariant): locked = locked.toBool()
        self.resize(size)
        self.move(pos)
        if state is not None:
            self.restoreState(state)
        self.ui.actionLocked.setChecked(bool(locked))

    def saveApplicationSettings(self):
        settings = QSettings()
        settings.setValue("MainWindow/Size", self.size())
        settings.setValue("MainWindow/Position", self.pos())
        settings.setValue("MainWindow/State", self.saveState())
        settings.setValue("MainWindow/ViewsLocked", self.ui.actionLocked.isChecked())
        if self.labeltool.getCurrentFilename() is not None:
            filename = self.labeltool.getCurrentFilename()
        else:
            filename = None
        settings.setValue("LastFile", filename)

    def okToContinue(self):
        if self.labeltool.model().dirty():
            reply = QMessageBox.question(self,
                                         "%s - Unsaved Changes" % (APP_NAME),
                                         "Save unsaved changes?",
                                         QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if reply == QMessageBox.Cancel:
                return False
            elif reply == QMessageBox.Yes:
                return self.fileSave()
        return True

    # 新建Annotations
    def fileNew(self):
        """
        新建Annotations
        """
        if self.okToContinue():
            self.labeltool.clearAnnotations()

    # 打开Annotations
    def fileOpen(self):
        """
        打开Annotations
        """
        if not self.okToContinue():
            return
        path = '.'
        filename = self.labeltool.getCurrentFilename()
        if (filename is not None) and (len(filename) > 0):
            path = QFileInfo(filename).path()

        format_str = ' '.join(self.labeltool.getAnnotationFilePatterns())
        fname = QFileDialog.getOpenFileName(self,
                                            "%s - Load Annotations" % APP_NAME, path,
                                            "%s annotation files (%s)" % (APP_NAME, format_str))
        if len(str(fname)) > 0:
            self.labeltool.loadAnnotations(fname)

    # 保存
    def fileSave(self):
        """
        保存
        :return:
        """
        return self.labeltool.saveAnnotations(None, self.mode.text() == '测试标定模式', pre=-1,
                                              all_flag=self.save_all_mode.text() == '保存全部图片')

    # 另保存
    def fileSaveAs(self):
        """
        另保存
        """
        fname = '.'  # self.annotations.filename() or '.'
        format_str = ' '.join(self.labeltool.getAnnotationFilePatterns())
        fname = QFileDialog.getSaveFileName(self,
                                            "%s - Save Annotations" % APP_NAME, fname,
                                            "%s annotation files (%s)" % (APP_NAME, format_str))

        if len(str(fname)) > 0:
            return self.labeltool.saveAnnotations(str(fname))
        return False

    # 添加图片
    def addMediaFile(self):
        """
        添加图片
        """
        path = '.'
        filename = self.labeltool.getCurrentFilename()
        if (filename is not None) and (len(filename) > 0):
            path = QFileInfo(filename).path()

        image_types = ['*.jpg', '*.bmp', '*.png', '*.pgm', '*.ppm', '*.tiff', '*.tif', '*.gif']
        video_types = ['*.mp4', '*.mpg', '*.mpeg', '*.avi', '*.mov', '*.vob']
        format_str = ' '.join(image_types + video_types)
        fnames = QFileDialog.getOpenFileNames(self, "%s - Add Media File" % APP_NAME, path,
                                              "Media files (%s)" % (format_str,))
        if fnames is None or fnames == []:
            return
        item = None
        numFiles = len(fnames)
        progress_bar = QProgressDialog('Importing files...', 'Cancel import', 0, numFiles, self)
        for fname, c in zip(fnames, range(numFiles)):
            if len(str(fname)) == 0:
                continue
            fname = str(fname)
            if os.path.isabs(fname):
                # fname = os.path.relpath(fname, str(path))
                fname = self.real_path(fname, str(path))
            ann = set()
            # 获得当前加的图片的绝对路径
            for temp in self.labeltool._model.root().getAnnotations():
                ann.add(temp['filename'])
            if fname in ann:
                return
            for pattern in image_types:
                if fnmatch.fnmatch(fname.lower(), pattern):
                    item = self.labeltool.addImageFile(fname)
                    break

            progress_bar.setValue(c)

        if item is None:
            return self.labeltool.addVideoFile(fname)

        progress_bar.close()

        return item

    # 读取文件夹所有图片
    def addMediaFile1(self):
        """
        读取文件夹的所有含merge的图片
        """
        path = '.'
        image_types = ['*.jpg', '*.bmp', '*.png', '*.pgm', '*.ppm', '*.tiff', '*.tif', '*.gif']
        directory = QFileDialog.getExistingDirectory(self)
        fnames = Main.get_merged_pictures(directory, None)
        numFiles = len(fnames)
        progress_bar = QProgressDialog('Importing files...', 'Cancel import', 0, numFiles, self)
        item = None
        for fname, c in zip(fnames, range(numFiles)):
            if '*' + os.path.splitext(fname)[-1].lower() in image_types:
                item = self.labeltool.addImageFile(self.real_path(fname, path))
            progress_bar.setValue(c)
        if item is None:
            return self.labeltool.addVideoFile(fname)
        progress_bar.close()
        return item

    def onViewsLockedChanged(self, checked):
        features = QDockWidget.AllDockWidgetFeatures
        if checked:
            features = QDockWidget.NoDockWidgetFeatures

        self.ui.dockProperties.setFeatures(features)
        self.ui.dockAnnotations.setFeatures(features)

    def onMousePress(self):
        self.listenMouse = True

    def onMouseRelease(self):
        self.listenMouse = False

    # 键盘监听
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Control or event.key == Qt.Key_Shift or event.key == Qt.Key_Alt:
            event.accept()
            return
        uKey = event.key()
        modifiers = event.modifiers()
        if modifiers & Qt.ControlModifier:
            uKey += Qt.Key_Control
        if modifiers & Qt.ShiftModifier:
            uKey += Qt.Key_Shift
        if modifiers & Qt.AltModifier:
            uKey += Qt.Key_Alt
        if uKey == Qt.Key_Z + Qt.Key_Control + Qt.Key_Alt:
            if self.scene._inserter is not None:
                if type(self.scene._inserter) == inserters.PolygonItemInserter:
                    if self.scene._inserter._item is not None:
                        return
                self.scene._inserter.abort()
                del self.scene._inserter
                self.scene._inserter = None
            event.ignore()
        elif uKey == Qt.Key_Z + Qt.Key_Control:
            if self.scene._inserter is not None:
                if type(self.scene._inserter) == inserters.PolygonItemInserter:
                    if self.scene._inserter._item is not None:
                        return
            self.undo()
            event.accept()
        elif uKey == Qt.Key_Z + Qt.Key_Control + Qt.Key_Shift:
            if self.scene._inserter is not None:
                if type(self.scene._inserter) == inserters.PolygonItemInserter:
                    if self.scene._inserter._item is not None:
                        return
            self.redo()
            event.accept()
        else:
            try:
                MainWindow.keyPressEvent(event)
            except TypeError:
                pass

    # 关闭事件
    def closeEvent(self, event):
        if self.okToContinue():
            self.saveApplicationSettings()
        else:
            event.ignore()

    def about(self):
        QMessageBox.about(self, "About %s" % APP_NAME,
                          """<b>%s</b> version
             <p>modified by Nightmare4214|yun_di"""
                          % 1.3, )
