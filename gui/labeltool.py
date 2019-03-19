#!/usr/bin/python
import json
import fnmatch
import functools
import logging
import os
import platform
import sys

import PyQt4.uic as uic
import json5
import sloth.Main as Main
from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import QSettings, QSize, QPoint, QVariant, QFileInfo, QTimer, pyqtSignal, QObject, Qt
from PyQt4.QtGui import QMainWindow, QSizePolicy, QWidget, QVBoxLayout, QAction, \
    QKeySequence, QLabel, QItemSelectionModel, QMessageBox, QFileDialog, QFrame, \
    QDockWidget, QProgressBar, QProgressDialog, QCursor, QGraphicsPolygonItem
from sloth import APP_NAME, ORGANIZATION_DOMAIN
from sloth.annotations.container import AnnotationContainerFactory
from sloth.annotations.model import AnnotationTreeView, FrameModelItem, ImageFileModelItem, CopyAnnotations, \
    InterpolateRange
from sloth.conf import config
from sloth.core.utils import import_callable
from sloth.gui import qrc_icons  # needed for toolbar icons
from sloth.gui.annotationscene import AnnotationScene
from sloth.gui.controlbuttons import ControlButtonWidget
from sloth.gui.frameviewer import GraphicsView
from sloth.gui.propertyeditor import PropertyEditor
from sloth.utils.bind import bind, compose_noargs
import sloth.conf.default_config as cf

GUIDIR = os.path.join(os.path.dirname(__file__))

LOG = logging.getLogger(__name__)


class BackgroundLoader(QObject):
    finished = pyqtSignal()

    def __init__(self, model, statusbar, progress):
        QObject.__init__(self)
        self._max_levels = 3
        self._model = model
        self._statusbar = statusbar
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

    def load(self):
        if not self._message_displayed:
            self._statusbar.showMessage("Loading annotations...", 5000)
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

    def load_json(self):
        # 获取这次配置文件的路径
        direct = os.path.dirname(sys.argv[0])
        with open(os.path.join(direct, 'sloth.txt'), 'r') as f:
            label_path = f.read()
        temp = []
        try:
            with open(label_path, 'r') as f:
                temp = json5.load(f)
        except Exception as e:
            temp = []
        finally:
            LABELS = temp
        return LABELS

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

    def onCurrentImageChanged(self):
        new_image = self.labeltool.currentImage()
        self.scene.setCurrentImage(new_image)
        self.onFitToWindowModeChanged()
        self.treeview.scrollTo(new_image.index())

        img = self.labeltool.getImage(new_image)
        if img.any() == None:
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
    def showContextMenu(self):
        self.contextMenu.exec_(QCursor.pos())

    # 打开文件所在路径
    def openDirectory(self):
        a = self.to_image()
        # while a.parent
        annotations = self.labeltool.annotations()
        if a.row() < 0:
            return
        open_path = os.path.dirname(annotations[a.row()]['filename'])
        try:
            sysstr = platform.system()
            if sysstr == "Windows":
                os.system('explorer ' + open_path)
            elif sysstr == "Linux":
                os.system('nautilus ' + open_path)
            else:
                print("Other System tasks")
        except Exception as e:
            print(e)

    # 搜索文件
    def search_file(self):
        key_word = self.property_editor.get_key_word()
        extension = self.property_editor.get_extension().lower()
        if extension == 'json':
            self.add_all_json(key_word)
        else:
            directory = QFileDialog.getExistingDirectory(self)
            if self.mode.text() == '测试标定模式':
                test_image = os.path.join(directory, 'test_Images')
                print(test_image)
                if not os.path.exists(test_image):
                    os.mkdir(test_image)
            fnames = Main.get_merged_pictures(directory, key_word, extension)
            numFiles = len(fnames)
            progress_bar = QProgressDialog('Importing files...', 'Cancel import', 0, numFiles, self)
            item = None
            for fname, c in zip(fnames, range(numFiles)):
                item = self.labeltool.addImageFile(self.real_path(fname, '.'))
                progress_bar.setValue(c)
            progress_bar.close()
            return item

    # 改变部件可视
    def change_visible(self, action):
        state = action.isChecked()
        self.property_editor.component_visible(action.text(), not state)

    ###
    ### GUI/Application setup
    ###___________________________________________________________________________________________
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
        self.ui.dockProperties.setWidget(self.property_editor)

        # Scene
        self.scene = AnnotationScene(self.labeltool, items=items, inserters=inserters)
        self.property_editor.insertionModeStarted.connect(self.scene.onInsertionModeStarted)
        self.property_editor.insertionModeEnded.connect(self.scene.onInsertionModeEnded)

        self.property_editor._register = self.scene.add_label

        # SceneView
        self.view = GraphicsView(self)

        # 在图片上设置右键菜单
        self.contextMenu = QtGui.QMenu(self)
        self.actionA = self.contextMenu.addAction('打开文件所在文件夹')
        self.actionA.triggered.connect(self.openDirectory)
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.showContextMenu)
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
        self.treeview.set_openDirectory(self.openDirectory)
        self.treeview.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        self.ui.dockAnnotations.setWidget(self.treeview)

        self.scene.selectionChanged.connect(self.scene.onSelectionChanged)
        self.treeview.selectedItemsChanged.connect(self.scene.onSelectionChangedInTreeView)

        self.posinfo = QLabel("-1, -1")
        self.posinfo.setFrameStyle(QFrame.StyledPanel)
        self.statusBar().addPermanentWidget(self.posinfo)
        self.scene.mousePositionChanged.connect(self.onMousePositionChanged)

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

    def change_mode(self):
        if self.mode.text() == '训练标定模式':
            self.mode.setText('测试标定模式')
        else:
            self.mode.setText('训练标定模式')

    # 获得临时的json名字
    def get_name(self, temp_json_path='faQ.json'):
        while os.path.exists(temp_json_path):
            temp_json_path = os.path.splitext(temp_json_path)[0] + '(1)' + '.json'
        return temp_json_path

    # path和项目同盘符则返回相对start路径，否则返回绝对路径
    def real_path(self, path, start):
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
                    except Exception as e:
                        print('读取%s失败' % json_file)
                        continue
                    for i in range(len(temp)):
                        # 如果读进来是个json而不是json_array，将会报错
                        try:
                            current_json = temp[i]
                        except Exception as e:
                            break
                        # 判断filename在json中
                        if 'filename' in current_json and \
                                set(current_json.keys()).issubset({'annotations', 'class', 'filename'}):
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
        # 临时json
        temp_json_path = self.get_name()
        # 保存json
        container = AnnotationContainerFactory(config.CONTAINERS).create(temp_json_path)
        container.save(temp_json, temp_json_path)
        # 读入json
        self.labeltool.loadAnnotations(temp_json_path)
        # 删除临时的json
        os.remove(temp_json_path)

    # 撤回多边形，按照点撤回，如ABCDE->ABCD
    def undo_polygon(self, model_index):
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
        print('attribute_class', attribute_class)
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
            # inserter._updateAnnotation()
            # if inserter._commit:
            #     self.scene._image_item.addAnnotation(inserter._ann)
            # inserter.annotationFinished.emit()
            # self.scene.removeItem(item)
            # inserter._item = None
            # inserter.inserterFinished.emit()

    # 撤回
    def undo(self):
        a = self.to_image()
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
        data = []
        while last_child.child(i, 1).data() is None:
            child = last_child.child(i, 1)
            data.append(child.data())
            i += 1
        annotations = self.labeltool.annotations()
        if a.row() < 0:
            return
        # 获得文件
        open_path = annotations[a.row()]['filename']
        # 给文件加撤回列表
        if open_path not in self._item_dir:
            self._item_dir[open_path] = []
        print(last_child.data())
        print(last_child.child(0, 1).data())
        print(last_child.child(1, 1).data())
        self.treeview.setCurrentIndex(last_child)
        config = self.load_json()
        item_type = None
        for current_json in config:
            if current_json['attributes']['class'] == last_child.data():
                item_type = current_json['item']
                break
        for item in self.scene.selectedItems():
            if item_type == 'sloth.items.PointItem':
                data = item._point
            elif item_type == 'sloth.items.RectItem':
                data = item._rect
            elif item_type == 'sloth.items.PolygonItem':
                data = item._polygon
        self._item_dir[open_path].append([last_child.data(), item_type, data])
        self.scene.deleteSelectedItems()
        self.treeview.setCurrentIndex(a)

    # 重做（相当于ctrl+y或者ctrl+shift+z)
    def redo(self):
        a = self.to_image()
        annotations = self.labeltool.annotations()
        if a.row() < 0:
            self.treeview.setCurrentIndex(a)
            return
        open_path = annotations[a.row()]['filename']
        if open_path not in self._item_dir or len(self._item_dir[open_path]) == 0:
            return
        attribute_class = self._item_dir[open_path][-1][0]
        item_type = self._item_dir[open_path][-1][1]
        data = self._item_dir[open_path][-1][2]
        print('attribute_class', attribute_class)
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

    def connectActions(self):
        ## File menu
        self.ui.actionNew.triggered.connect(self.fileNew)
        self.ui.actionOpen.triggered.connect(self.fileOpen)
        self.ui.actionSave.triggered.connect(self.fileSave)
        self.ui.actionSave_As.triggered.connect(self.fileSaveAs)
        self.ui.actionExit.triggered.connect(self.close)

        ## View menu
        self.ui.actionLocked.toggled.connect(self.onViewsLockedChanged)

        ## Help menu
        self.ui.action_About.triggered.connect(self.about)

        ## Navigation
        self.ui.action_Add_Image.triggered.connect(self.addMediaFile)
        self.ui.action_Add_All_Image.triggered.connect(self.addMediaFile1)
        self.ui.actionAdd_Json.triggered.connect(self.add_json)
        self.ui.actionAdd_All_Json.triggered.connect(self.add_all_json)

        self.ui.actionNext.triggered.connect(self.labeltool.gotoNext)
        self.ui.actionPrevious.triggered.connect(self.labeltool.gotoPrevious)
        self.ui.actionZoom_In.triggered.connect(functools.partial(self.view.setScaleRelative, 1.2))
        self.ui.actionZoom_Out.triggered.connect(functools.partial(self.view.setScaleRelative, 1 / 1.2))
        self.ui.action_Undo.triggered.connect(self.undo)

        ## Connections to LabelTool
        self.labeltool.pluginLoaded.connect(self.onPluginLoaded)
        self.labeltool.statusMessage.connect(self.onStatusMessage)
        self.labeltool.annotationsLoaded.connect(self.onAnnotationsLoaded)
        self.labeltool.currentImageChanged.connect(self.onCurrentImageChanged)

        ## options menu
        self.options["Fit-to-window mode"].changed.connect(self.onFitToWindowModeChanged)
        self.options["Enumerate-corners mode"].changed.connect(self.onEnumerateCornersModeChanged)

        ## annotation menu
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
        if self.okToContinue():
            self.labeltool.clearAnnotations()

    # 打开Annotations
    def fileOpen(self):
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
        return self.labeltool.saveAnnotations(None, self.mode.text() == '测试标定模式')

    # 另保存
    def fileSaveAs(self):
        fname = '.'  # self.annotations.filename() or '.'
        format_str = ' '.join(self.labeltool.getAnnotationFilePatterns())
        fname = QFileDialog.getSaveFileName(self,
                                            "%s - Save Annotations" % APP_NAME, fname,
                                            "%s annotation files (%s)" % (APP_NAME, format_str))

        if len(str(fname)) > 0:
            return self.labeltool.saveAnnotations(str(fname))
        return False

    def addMediaFile(self):
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

            for pattern in image_types:
                if fnmatch.fnmatch(fname.lower(), pattern):
                    item = self.labeltool.addImageFile(fname)
                    break

            progress_bar.setValue(c)

        if item is None:
            return self.labeltool.addVideoFile(fname)

        progress_bar.close()

        return item

    # 读取文件夹的所有含merge的图片
    def addMediaFile1(self):
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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Control or event.key == Qt.Key_Shift or event.key == Qt.Key_Alt:
            return
        uKey = event.key()
        modifiers = event.modifiers()
        if modifiers & Qt.ControlModifier:
            uKey += Qt.Key_Control
        if modifiers & Qt.ShiftModifier:
            uKey += Qt.Key_Shift
        if uKey == Qt.Key_Z + Qt.Key_Control:
            self.undo()
            event.accept()
        elif uKey == Qt.Key_Z + Qt.Key_Control + Qt.Key_Shift:
            self.redo()
            event.accept()
        else:
            try:
                MainWindow.keyPressEvent(event)
            except TypeError:
                pass

    ###
    ### global event handling
    ###______________________________________________________________________________
    def closeEvent(self, event):
        if self.okToContinue():
            self.saveApplicationSettings()
        else:
            event.ignore()

    def about(self):
        QMessageBox.about(self, "About %s" % APP_NAME,
                          """<b>%s</b> version %s
             <p>This labeling application for computer vision research
             was developed at the CVHCI research group at KIT.
             <p>For more details, visit our homepage: <a href="%s">%s</a>"""
                          % (APP_NAME, __version__, ORGANIZATION_DOMAIN, ORGANIZATION_DOMAIN))
