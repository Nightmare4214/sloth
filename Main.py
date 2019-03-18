#!/usr/bin/env python
# _*_ coding:utf-8 _*_
from datetime import datetime
import json
import os


# 判断是否包含瑕疵
def contains_defect(annotations, defect_type):
    defects = set()
    for annotation in annotations:
        if 'class' in annotation:
            defects.add(annotation['class'])
    return defect_type.issubset(defects)


# 获得所有图片路径
# @param json_path json文件的文件夹
# @param defect_type 瑕疵类型集合(传入set)
def get_pictures(json_path, defect_type):
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


# 将json中拥有瑕疵的图片写入txt中
# @param json_directory json文件的文件夹
# @param defect 瑕疵类型集合(传入set)
# @param txt_path txt所属文件夹
def write_txt(json_directory, defect, txt_path):
    pictures = get_pictures(json_directory, defect)
    directory = os.path.join(json_directory, txt_path)
    if not os.path.exists(directory):
        os.makedirs(directory)
    with open(os.path.join(directory,
                           '.'.join(defect)+'_'+datetime.now().strftime('%Y_%m_%d_%H_%M_%S') + '.txt'), 'w') as f:
        # f.write(str(pictures))
        for picture in pictures:
            f.write(picture + '\n')


# 获得所有的合并后的图片（以key_word为前缀的图片）
# @param pictures_path 图片的文件夹
# @param key_word 标志位
# @param extension 扩展名
def get_merged_pictures(pictures_path, key_word='merge', extension=None):
    pictures_list = []
    for root, dirs, files in os.walk(pictures_path):
        for file in files:
            temp = os.path.splitext(file)
            if key_word is None or key_word is '' or temp[0].find(key_word) >= 0:
                if extension is None or temp[1] == '.' + extension:
                    pictures_list.append(os.path.abspath(os.path.join(root, file)))
    return pictures_list


if __name__ == '__main__':
    json_directory = r'E:\sloth\faQ'
    defect = {'rect'}
    txt_path = 'defect'
    write_txt(json_directory, defect, txt_path)
    # print(get_merged_pictures(r'E:\pyTest\sloth-master\examples', 'example'))
