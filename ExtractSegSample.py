# -*- coding: utf-8 -*-
import os
import random
import cv2
import numpy as np
import simplejson as json

from PIL import Image, ImageDraw, ImageFont

class2color = {}


def generate_sample(search_dir, search_name, save_dir, class2label, class2item, train_name='train.txt',
                    test_name='test.txt', index_name='index.txt', split_ratio=0.8, save_cnt=1, bshow=False,
                    crop_ratio_lrtd=None, do_shuffle=True, only_defect=True, all_contain=False,
                    multiply_flag=True, enable_all_zero=True):
    """
        将文件夹中所有的符合的图片的json转为图片，并按比例分割成训练集和测试集
        :param search_dir: 搜索路径
        :param search_name: 搜索名字
        :param save_dir: 保存路径
        :param class2label: 缺陷转像素
        :param class2item: 缺陷的形状
        :param train_name: 训练txt名字，只要文件名字，如train.txt，不要写绝对路径
        :param test_name: 测试txt名字，只要文件名字，如test.txt，不要写绝对路径
        :param index_name: 索引txt名字，只要文件名字，index.txt，不要写绝对路径
        :param split_ratio: 训练集比例，0-1之间，
        :param save_cnt: 计数开始
        :param bshow: 是否显示图片
        :param crop_ratio_lrtd: crop the image with ratio, l r t d ratio is specified
        :param do_shuffle: 打乱
        :param only_defect 只画defect中的缺陷类型
        :param all_contain 图片必须包含所有的要求缺陷
        :param multiply_flag: 像素放大
        :param enable_all_zero: 是否允许全0的图，即允许有不往上画任何东西的图
        """
    if split_ratio > 1 or split_ratio < 0:
        return
    cnt = 0
    if crop_ratio_lrtd is None:
        crop_ratio_lrtd = []
    # 目录不存在，则创建
    if not os.path.exists(save_dir):
        os.mkdir(save_dir)
    all_save_label_names = []
    findex = open(os.path.join(save_dir, index_name), "w")
    search_name = os.path.basename(search_name)
    # 搜索图片名字去掉扩展名
    json_name = os.path.splitext(search_name)[0] + '.json'
    # 遍历
    for root, dirs, files in os.walk(search_dir):
        for file in files:
            if file != json_name:
                continue
            json_array_path = os.path.join(root, file)
            with open(json_array_path, 'r') as f:
                json_array = json.load(f)
            for cur_json in json_array:
                defect_set = set()
                img_ful_filename = os.path.join(root, cur_json['filename'])
                if not os.path.exists(img_ful_filename) or 'annotations' not in cur_json:
                    continue
                annotations = cur_json['annotations']
                if len(annotations) == 0:
                    continue
                # 画的点，灰度值
                contours, labels = [], []
                # 遍历annotations
                for annotation in annotations:
                    if 'class' in annotation and annotation["class"] in class2label:
                        defect_set.add(annotation['class'])
                        # 只要在defect中
                        if only_defect and annotation['class'] not in class2label:
                            continue
                        labels.append(annotation["class"])
                    else:
                        continue
                    # 多边形
                    if 'xn' in annotation and 'yn' in annotation:
                        xn = np.array([float(b) for b in annotation["xn"].split(";")], int)
                        yn = np.array([float(b) for b in annotation["yn"].split(";")], int)
                        cur_contour = np.hstack([xn[:, np.newaxis], yn[:, np.newaxis]])
                        cur_contour1 = cur_contour[:, np.newaxis, :]
                        contours.append(cur_contour1)
                    # 矩形
                    elif 'x' in annotation and 'y' in annotation and 'height' in annotation and 'width' in annotation:
                        x = int(annotation["x"])
                        y = int(annotation["y"])
                        height = int(annotation["height"])
                        width = int(annotation["width"])
                        contours.append([(x, y), (x + width, y + height)])
                    # 点
                    elif 'x' in annotation and 'y' in annotation and 'height' not in annotation and 'width' not in annotation:
                        x = int(annotation["x"])
                        y = int(annotation["y"])
                        contours.append((x, y))
                # 必须包含所有的缺陷
                if all_contain and not set(class2label.keys()).issubset(defect_set):
                    continue
                # 不允许全0的图
                if not enable_all_zero and len(labels) < 1:
                    continue
                # 中文路径读图
                img = cv2.imdecode(np.fromfile(img_ful_filename, dtype=np.uint8), -1)
                # 黑底图片
                label_img = np.zeros((img.shape[:2]), np.uint8)
                r = list(zip(labels, contours))
                r = sorted(r, key=lambda t: class2label[t[0]])
                # 画图
                for i, j in r:
                    if class2item[i] == 'PolygonItem':
                        cv2.drawContours(label_img, [j], -1, class2label[i], -1)
                    elif class2item[i] == 'PointItem':
                        cv2.circle(label_img, j, 4, class2label[i], -1)
                    elif class2item[i] == 'RectItem':
                        cv2.rectangle(label_img, j[0], j[1], class2label[i], -1)
                # 裁剪
                if crop_ratio_lrtd is not None and len(crop_ratio_lrtd) == 4:
                    sx, sy = int(crop_ratio_lrtd[0] * label_img.shape[1]), int(
                        crop_ratio_lrtd[2] * label_img.shape[0])
                    ex, ey = int((1.0 - crop_ratio_lrtd[1]) * label_img.shape[1]), int(
                        (1.0 - crop_ratio_lrtd[3]) * label_img.shape[0])
                    img, label_img = img[sy:ey, sx:ex], label_img[sy:ey, sx:ex]
                # 乘完看起来就不是全黑的
                if multiply_flag:
                    label_img = label_img * (255 / max(class2label.values()))
                # 显示图片
                if bshow:
                    cv2.namedWindow('img', cv2.WINDOW_NORMAL)
                    cv2.imshow('img', img)
                    cv2.namedWindow('label_img', cv2.WINDOW_NORMAL)
                    cv2.imshow('label_img', label_img)
                    # print "label is {}".format(labels)
                    cv2.waitKey(10)
                # 图片原始路径
                write_text = img_ful_filename
                # 图片名字,图片扩展名
                temp_json_name, image_ext = os.path.splitext(os.path.basename(write_text))
                # 先给他5位
                cnt_str = str.zfill(str(save_cnt), 5)
                # json转换后的图片路径
                save_label_path = os.path.join(save_dir, temp_json_name + cnt_str + "_label" + image_ext)
                # 保存json转换后的图片
                cv2.imencode(image_ext, label_img)[1].tofile(save_label_path)
                # 原始图片图片路径
                save_src_path = os.path.join(save_dir, temp_json_name + cnt_str + image_ext)
                write_text = save_src_path
                # 保存原始图片图片
                cv2.imencode(image_ext, img)[1].tofile(save_src_path)
                findex.write(os.path.basename(write_text) + ' ' + os.path.dirname(root) + '\n')
                all_save_label_names.append(
                    os.path.basename(write_text) + "  " + os.path.basename(save_label_path) + '\n')
                save_cnt += 1
                cnt += 1
    findex.close()
    # 打乱
    if do_shuffle:
        random.shuffle(all_save_label_names)
    # 训练集个数
    train_cnt = int(len(all_save_label_names) * split_ratio)
    ftrain = open(os.path.join(save_dir, train_name), "w")
    ftest = open(os.path.join(save_dir, test_name), "w")
    # 根据比例分割
    for i, save_label_path in enumerate(all_save_label_names):
        if i < train_cnt:
            fwrite = ftrain
        else:
            fwrite = ftest
        fwrite.write(save_label_path)
    ftrain.close()
    ftest.close()


# 更新class2color
def update(config_path):
    # 读配置文件
    with open(config_path, 'r') as f:
        json_conf = json.load(f)
    # 标签转颜色
    global class2color
    class2color = {}
    for current_json in json_conf:
        # 字符串转数字，从RGB转opencv的BGR
        # class2color[current_json['attributes']['class']] = list(map(int, current_json['color'].split(',')))[::-1]
        # 字符串转数字
        class2color[current_json['attributes']['class']] = list(map(int, current_json['color'].split(',')))[::-1]


def generate_jpg(json_file, save_dir, font_size=10, thickness=1):
    """
    将json花在对应的图片上，按照jpg和json存入save_dir
    :param json_file:json文件绝对路径
    :param save_dir:保存的目录绝对路径
    :param font_size: 字体大小
    :param thickness: 线条粗细
    """
    if not os.path.exists(json_file):
        return
    if not os.path.exists(save_dir):
        os.mkdir(save_dir)
    global class2color
    # 读json
    with open(json_file, 'r') as f:
        json_array = json.load(f)
    # 目录
    dir = os.path.dirname(json_file)
    for current_json in json_array:
        filename = current_json['filename']
        filename = os.path.join(dir, filename)
        if not os.path.exists(filename):
            continue
        # 中文路径读图
        img = cv2.imdecode(np.fromfile(filename, dtype=np.uint8), 1)
        # img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        annotations = current_json['annotations']
        text_queue = []
        for annotation in annotations:
            text = annotation['class']
            color = class2color[text]
            # 读形状
            if 'height' in annotation and 'width' in annotation and 'x' in annotation and 'y' in annotation:
                x = int(annotation["x"])
                y = int(annotation["y"])
                height = int(annotation["height"])
                width = int(annotation["width"])
                cv2.rectangle(img, (x, y), (x + width, y + height), color, thickness)
            elif 'height' not in annotation and 'width' not in annotation and 'x' in annotation and 'y' in annotation:
                x = int(annotation["x"])
                y = int(annotation["y"])
                cv2.circle(img, (x, y), 4, color, thickness)
            elif 'xn' in annotation and 'yn' in annotation:
                xn = np.array([float(b) for b in annotation["xn"].split(";")], int)
                yn = np.array([float(b) for b in annotation["yn"].split(";")], int)
                cur_contour = np.hstack([xn[:, np.newaxis], yn[:, np.newaxis]])
                cur_contour1 = cur_contour[:, np.newaxis, :]
                cv2.drawContours(img, [cur_contour1], -1, color, thickness)
                x = xn[0]
                y = yn[0]
            else:
                continue
            text_queue.append((text, x, y, tuple(color)))
            # text_queue.append((text, x, y, tuple(color[::-1])))
        # cv2.imshow('test', img)
        # cv2.waitKey(0)
        # 转成PIL的
        img = Image.fromarray(img)
        for text, x, y, color in text_queue:
            draw = ImageDraw.Draw(img)
            fontText = ImageFont.truetype(
                "font/simsun.ttc", font_size, encoding="utf-8")
            # 写字
            draw.text((x, y), text, color, font=fontText)
        img = np.asarray(img)
        # 转回opencv的BGR
        # img = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
        # cv2.imshow('test', img)
        # cv2.waitKey(0)
        image_name, image_ext = os.path.splitext(os.path.basename(filename))
        image_save_path = os.path.join(save_dir, image_name + '.jpg')
        cv2.imencode('.jpg', img)[1].tofile(image_save_path)
