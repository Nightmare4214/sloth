#!/usr/bin/env python
# _*_ coding:utf-8 _*_
from datetime import datetime
import json
import os
import sys
import json5


def contains_defect(annotations, defect_type):
    """
    判断是否包含瑕疵
    :param annotations:
    :param defect_type:
    :return:
    """
    defects = set()
    for annotation in annotations:
        if 'class' in annotation:
            defects.add(annotation['class'])
    return defect_type.issubset(defects)


def get_pictures(json_path, defect_type):
    """
    获得所有图片路径
    :param json_path: json文件的文件夹
    :param defect_type: 瑕疵类型集合(传入set)
    :return: 图片的绝对路径
    """
    pictures = set()
    # 遍历文件夹中的所有文件
    for root, dirs, files in os.walk(json_path):
        for file in files:
            if os.path.splitext(file)[-1] == '.json':
                json_file = os.path.join(root, file)
                with open(json_file, 'r') as f:
                    temp = json.load(f)
                for i in range(len(temp)):
                    current_json = temp[i]
                    if contains_defect(current_json['annotations'], defect_type):
                        pictures.add(os.path.abspath(os.path.join(root, current_json['filename'])))
    return pictures


def write_txt(json_directory, defect, txt_path):
    """
    将json中拥有瑕疵的图片写入txt中
    :param json_directory: json文件的文件夹
    :param defect: 瑕疵类型集合(传入set)
    :param txt_path: txt所属文件夹
    """
    pictures = get_pictures(json_directory, defect)
    directory = os.path.join(json_directory, txt_path)
    if not os.path.exists(directory):
        os.makedirs(directory)
    with open(os.path.join(directory,
                           '.'.join(defect) + '_' + datetime.now().strftime('%Y_%m_%d_%H_%M_%S') + '.txt'), 'w') as f:
        for picture in pictures:
            f.write(picture + '\n')

def isConfig(configure : list):
    inserterValue = ["sloth.items.RectItemInserter", "sloth.items.PointItemInserter","sloth.items.PolygonItemInserter"]
    itemValue = ["sloth.items.RectItem", "sloth.items.PointItem","sloth.items.PolygonItem"]
    valueList = []
    try:
        if not isinstance(configure, list) or len(configure)<1:
            return False
        for item in configure:
            if not {'attributes','inserter', 'item', 'color', 'brush', 'text'}.issubset(set(item.keys())):
                return False
            for key,value in item.items():
                if 'attributes' == key:
                    if 'class' not in value or value['class'] in valueList:
                        return False
                    valueList.append(value['class'])
                elif 'brush' == key:
                    bruInt = int(value)
                    if not 0 <= bruInt < 18:
                        return False
                elif 'color' == key:
                    r,g,b=map(int,value.split(','))
                    if not (0 <= r < 256 and 0 <= g < 256 and 0 <= b < 256) :
                        return False
                elif 'hotkey' == key:
                    if not (value.islower() or value.isnumeric()) or len(value) != 1:
                        return False
                elif 'inserter' == key:
                    if value not in inserterValue:
                        return False
                    temp_insert = value
                elif 'item' == key:
                    if value not in itemValue:
                        return False
                    temp_item = value
            if not temp_insert.startswith(temp_item):
                return False
    except:
        return False
    return True

def get_merged_pictures(pictures_path, key_word='merge', extension=None):
    """
    获得所有的合并后的图片（以key_word为前缀的图片）
    :param pictures_path: 图片的文件夹
    :param key_word: 标志位
    :param extension: 扩展名
    :return: 图片的绝对路径的list
    """
    pictures_list = []
    for root, dirs, files in os.walk(pictures_path):
        for file in files:
            temp = os.path.splitext(file)
            if key_word is None or key_word is '' or temp[0].find(key_word) >= 0:
                if extension is None or temp[1].lower() == '.' + extension:
                    pictures_list.append(os.path.abspath(os.path.join(root, file)))
    return pictures_list


def get_json():
    """
    获取这次配置文件
    :return: 配置文件
    """
    # 获取这次配置文件的路径
    direct = os.path.dirname(sys.argv[0])
    try:
        with open(os.path.join(direct, 'sloth.txt'), 'r') as f:
            label_path = f.read()
        # 读取配置文件
        with open(label_path, 'r') as f:
            json_conf = json5.load(f)
        return json_conf
    except Exception as e:
        print(e)
        return []
