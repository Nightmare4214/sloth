# -*- coding: utf-8 -*-
import os
import sys

import cv2
import numpy as np
import simplejson as json


# generate training / testing samples & labels from .json file and split according to split ratio
# cur_file: the .json file
# ftrain, ftest: the file handle to write the directory to
# save_dir: if default, will save under the directory of cur_file, else will save under this directory
# save_cnt: current save_cnt for naming to saving names
# crop_ratio_lrtd: crop the image with ratio, l r t d ratio is specified
def generate_sample(search_dir,search_name, train_name='train.txt', test_name='test.txt', index_name='index.txt', split_ratio=0.8,
                    save_cnt=1, bshow=False, crop_ratio_lrtd=None, save_dir=""):
    dir_name = os.path.dirname(search_name)
    save_src_img = True  # whether we want to save the source image as well
    if save_dir == "":
        save_dir = os.path.join(dir_name, "label_images")
        save_src_img = False  # no need to save source image
    ftrain = open(os.path.join(save_dir, train_name), "w")
    ftest = open(os.path.join(save_dir, test_name), "w")
    findex = open(os.path.join(save_dir, index_name), "w")
    for root, dirs, files in os.walk(search_dir):

    if crop_ratio_lrtd is None:
        crop_ratio_lrtd = []
    if not os.path.exists(save_dir):
        os.mkdir(save_dir)
    with open(search_name) as f:
        json_array = json.load(f)
    # labels = json.load(open(cur_file))
    # 读取配置文件路径
    direct = os.path.dirname(sys.argv[0])
    with open(os.path.join(direct, './bin/sloth.txt'), 'r') as f:
        fname = f.read()
    # 读取配置文件
    with open(fname, 'r') as f:
        json_conf = json.load(f)
    class2label = {}
    # id转为类型
    idx2type = {}
    for i, current_json in enumerate(json_conf):
        class2label[current_json['attributes']['class']] = i + 1
        idx2type[i + 1] = current_json['item'].split('.')[-1]
    all_save_label_names = []
    # Use multiple labels instead of just one single label
    # 类型计数器
    class_cnt = dict(zip(class2label.keys(), [0] * len(class2label)))
    for cur_json in json_array:
        img_ful_filename = os.path.join(dir_name, cur_json['filename'])
        if os.path.exists(img_ful_filename):  # get the label and name
            annotations = cur_json['annotations']
            if len(annotations) == 0:
                continue
            contours, labels = [], []
            for annotation in annotations:
                if annotation["class"] in class2label:
                    labels.append(class2label[annotation["class"]])
                    class_cnt[annotation["class"]] += 1
                else:
                    break
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
            img = cv2.imread(img_ful_filename, cv2.IMREAD_UNCHANGED)

            # def filter_img(img):
            #     blured_img = cv2.medianBlur(img, 5)
            #     return blured_img
            # img = filter_img(img)
            # 黑底图片
            label_img = np.zeros((img.shape[0:2]), np.uint8)
            # 画图
            for i in range(len(contours)):
                if idx2type[labels[i]] == 'PolygonItem':
                    cv2.drawContours(label_img, [contours[i]], -1, (labels[i]), -1)
                elif idx2type[labels[i]] == 'PointItem':
                    cv2.circle(label_img, contours[i], 4, (labels[i]), -1)
                elif idx2type[labels[i]] == 'RectItem':
                    cv2.rectangle(label_img, contours[i][0], contours[i][1], (labels[i]), -1)
            # 裁剪
            if crop_ratio_lrtd is not None and len(crop_ratio_lrtd) == 4:
                sx, sy = int(crop_ratio_lrtd[0] * label_img.shape[1]), int(crop_ratio_lrtd[2] * label_img.shape[0])
                ex, ey = int((1.0 - crop_ratio_lrtd[1]) * label_img.shape[1]), int(
                    (1.0 - crop_ratio_lrtd[3]) * label_img.shape[0])
                img, label_img = img[sy:ey, sx:ex], label_img[sy:ey, sx:ex]
            print(class2label)
            # 显示图片
            if bshow:
                cv2.namedWindow('img', cv2.WINDOW_NORMAL)
                cv2.imshow('img', img)
                cv2.namedWindow('label_img', cv2.WINDOW_NORMAL)
                cv2.imshow('label_img', label_img * (255 / max(class2label.values())))
                # print "label is {}".format(labels)
                cv2.waitKey(10)
            # 图片原始路径
            write_text = img_ful_filename
            # 图片名字,图片扩展名
            image_name, image_ext = os.path.splitext(os.path.basename(write_text))
            # json转换后的图片路径
            save_label_name = os.path.join(save_dir, image_name +
                                           str(save_cnt) + "_label" + image_ext)
            # 保存
            cv2.imwrite(save_label_name, label_img * (255 / max(class2label.values())))
            # 保存原始图片图片
            if save_src_img:
                save_src_name = os.path.join(save_dir, image_name +
                                             str(save_cnt) + image_ext)
                write_text = save_src_name
                cv2.imwrite(save_src_name, img)
            all_save_label_names.append(os.path.basename(write_text) + "  " + os.path.basename(save_label_name) + '\n')
            save_cnt += 1
        else:
            print("warning not exists: " + img_ful_filename)

    train_cnt = int(len(all_save_label_names) * split_ratio)
    print('train cnt is {} and test cnt is {}'.format(
        train_cnt, len(all_save_label_names) - train_cnt))
    # 根据比例分割
    for i, save_label_name in enumerate(all_save_label_names):
        if i < train_cnt:
            fwrite = ftrain
        else:
            fwrite = ftest
        fwrite.write(save_label_name)
    ftrain.close()
    ftest.close()
    findex.close()
    return save_cnt

if __name__ == '__main__':
    # crop_ratio_lrtd = [0.0, 0.0, 0.0, 0.0]
    split_ratio = 0.98
    dst_dir = r'E:\task\sloth'
    json_files = [
        r'E:\deeplearn\mxnet\face_image\face0.json'
    ]
    save_train_txt = os.path.join(dst_dir, 'train.txt')
    save_test_txt = os.path.join(dst_dir, 'test.txt')
    save_index_txt = os.path.join(dst_dir, 'index.txt')
    save_cnt = 1
    crop_ratio_lrtd = None
    for cur_file in json_files:
        save_cnt = generate_sample(cur_file, save_cnt=save_cnt, bshow=True, save_dir=dst_dir)
        # save_cnt = generate_sample(cur_file, save_train_txt, save_test_txt, save_index_txt, split_ratio, save_cnt,
        # True,crop_ratio_lrtd=crop_ratio_lrtd, save_dir=dst_dir)

    # crop_ratio_lrtd = [0.93, 0.0, 0.0, 0.0]
    # crop_ratio_lrtd = [0.0, 0.0, 0.0, 0.0]
    # split_ratio = 0.02
