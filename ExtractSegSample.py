# -*- coding: utf-8 -*-
import os
import cv2
import numpy as np
import simplejson as json


def filter_img(img):
    blured_img = cv2.medianBlur(img, 5)
    return blured_img


# generate training / testing samples & labels from .json file and split according to split ratio
# cur_file: the .json file
# ftrain, ftest: the file handle to write the directory to
# save_dir: if default, will save under the directory of cur_file, else will save under this directory
# save_cnt: current save_cnt for naming to saving names
# crop_ratio_lrtd: crop the image with ratio, l r t d ratio is specified
def generate_sample(cur_file, ftrain, ftest, split_ratio, save_cnt, bshow=False, crop_ratio_lrtd=None, save_dir=""):
    if crop_ratio_lrtd is None:
        crop_ratio_lrtd = []
    dir_name = os.path.dirname(cur_file)
    save_src_img = True  # whether we want to save the source image as well
    if save_dir == "":
        save_dir = os.path.join(dir_name, "label_images")
        save_src_img = False  # no need to save source image
    if not os.path.exists(save_dir):
        os.mkdir(save_dir)
    with open(cur_file) as f:
        labels = json.load(f)
    # labels = json.load(open(cur_file))
    all_save_label_names = []
    # Use multiple labels instead of just one single label
    # class2label = {"dot_ao": 1, "dot_tu": 1, "heng_qi": 1, "heng_luo": 1, "huaheng": 1, "other": 1}
    # class2label = {"dot_ao":1, "dot_tu":2, "heng_qi":3, "heng_luo":4, "huaheng":5, "other":6}
    # class2label = {"metalbare": 1}
    class2label = {"polygon": 1}
    # class2label = {"huashang": 1}
    # class2label = {"heng_qi": 1}
    # class2label = {"heng_qi": 1}
    class_cnt = dict(zip(class2label.keys(), [0] * len(class2label)))
    for cur_label in labels:
        img_ful_filename = os.path.join(dir_name, cur_label['filename'])
        if os.path.exists(img_ful_filename):  # get the label and name
            annot = cur_label['annotations']
            if len(annot) == 0:
                # print 'no bb data in image {}'.format(img_filename)
                continue
            # true_annot = [a for a in annot if a['class'] in ['polygon', 'dot_ao'] ]  # the annotation may contains
            # detected
            true_annot = annot  # Use all the annotator
            if len(true_annot) == 0:
                continue

            contours, labels = [], []
            for a in true_annot:
                if a["class"] in class2label:
                    labels.append(class2label[a["class"]])
                    class_cnt[a["class"]] += 1
                elif "other" in class2label:
                    labels.append(class2label["other"])
                    class_cnt["other"] += 1
                else:
                    break
                xn = np.array([float(b) for b in a["xn"].split(";")], int)
                yn = np.array([float(b) for b in a["yn"].split(";")], int)
                cur_contour = np.hstack([xn[:, np.newaxis], yn[:, np.newaxis]])
                cur_contour1 = cur_contour[:, np.newaxis, :]
                contours.append(cur_contour1)

            img = cv2.imread(img_ful_filename, cv2.IMREAD_UNCHANGED)
            # img = filter_img(img)

            # ret_, binary_img = cv2.threshold(img, 210, 255, 0)
            # _, contours_true, hierarchy = cv2.findContours(binary_img, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

            label_img = np.zeros((img.shape[0], img.shape[1]), np.uint8)
            label_img[:] = 0
            print(labels)
            for i in range(len(contours)):
                cv2.drawContours(label_img, [contours[i]], -1, (labels[i]), -1)

            if crop_ratio_lrtd is not None and len(crop_ratio_lrtd) == 4:
                sx, sy = int(crop_ratio_lrtd[0] * label_img.shape[1]), int(crop_ratio_lrtd[2] * label_img.shape[0])
                ex, ey = int((1.0 - crop_ratio_lrtd[1]) * label_img.shape[1]), int(
                    (1.0 - crop_ratio_lrtd[3]) * label_img.shape[0])
                img, label_img = img[sy:ey, sx:ex], label_img[sy:ey, sx:ex]
            print(class2label)
            if bshow:
                cv2.imshow('img', img)
                cv2.imshow('label_img', label_img * (255 / max(class2label.values())))
                # print "label is {}".format(labels)
                cv2.waitKey(10)
            write_text = img_ful_filename
            save_label_name = os.path.join(save_dir,
                                           "label_" + str(save_cnt) + "_" + os.path.basename(img_ful_filename))
            cv2.imwrite(save_label_name, label_img * (255 / max(class2label.values())))
            if save_src_img:
                save_src_name = os.path.join(save_dir,
                                             "src_" + str(save_cnt) + "_" + os.path.basename(img_ful_filename))
                write_text = save_src_name
                # cv2.imwrite(save_src_name, img[:, :, 2]) #{ param::Picture_Blue, param::Picture_Red ,
                # param::Picture_Green }
                cv2.imwrite(save_src_name, img)  # { param::Picture_Blue, param::Picture_Red , param::Picture_Green }
            all_save_label_names.append(write_text + "  " + save_label_name + '\n')
            save_cnt += 1
        else:
            print("warning not exists: " + img_ful_filename)
    train_cnt = int(len(all_save_label_names) * (1.0 - split_ratio))
    print('train cnt is {} and test cnt is {}'.format(train_cnt, len(all_save_label_names) - train_cnt))
    print("key is {}".format(class_cnt.keys()))
    print("value is {}".format(class_cnt.values()))
    for i in range(len(all_save_label_names)):
        if i < train_cnt:
            fwrite = ftrain
        else:
            fwrite = ftest
        fwrite.write(all_save_label_names[i])
    return save_cnt


if __name__ == '__main__':
    print('faQ')
    crop_ratio_lrtd = [0.0, 0.0, 0.0, 0.0]
    split_ratio = 0.02
    dst_dir = r'E:\sloth_test\train_imgs'
    json_files = [
        r'E:\sloth_test\test\Y84PD46173062\merge_Y84PD46173062.json'
    ]
    save_train_txt = os.path.join(dst_dir, 'train.txt')
    save_test_txt = os.path.join(dst_dir, 'test.txt')
    ftrain = open(save_train_txt, "w")
    ftest = open(save_test_txt, "w")

    save_cnt = 0
    crop_ratio_lrtd = None
    for cur_file in json_files:
        save_cnt = generate_sample(cur_file, ftrain, ftest, split_ratio, save_cnt, True,
                                   crop_ratio_lrtd=crop_ratio_lrtd, save_dir=dst_dir)
    ftrain.close()
    ftest.close()

    # json_files_battery = [  # the battery files
    #     r"H:\code\parttime\glass_screen\data\uneven\convexepirelief\0e2e.json",
    #     r"h:\code\parttime\glass_screen\data\uneven\dent\1239.json",
    #     r"H:\code\parttime\glass_screen\data\uneven\getaliquid\085c.json",
    #     r"H:\code\parttime\glass_screen\data\uneven\scrictch\3138.json",
    #     r"H:\code\parttime\glass_screen\data\uneven\waterripple\1\1f26.json",
    #     r"H:\code\parttime\glass_screen\data\uneven\waterripple\2\1f1e.json",
    #     r"H:\code\parttime\glass_screen\data\uneven\waterripple\3\d0d1.json",
    # ]
    # json_files = [
    #     r"h:\code\parttime\glass_screen\data\mura_mark_photo_0413\1-25\1-25information.json",
    #     r"H:\code\parttime\glass_screen\data\mura_mark_photo_0413\26-54\26-54information.json",
    #     r"H:\code\parttime\glass_screen\data\mura_mark_photo_0413\55-83\55-83.json",
    #     r"H:\code\parttime\glass_screen\data\mura_mark_photo_0413\84-116\84-116.json",
    # ]
    # json_files = [  # head region dataset
    #     # r"H:\code\parttime\glass_screen\data\uneven\convexepirelief\0e2e.json",
    #     # r"H:\code\parttime\glass_screen\data\uneven\convexepirelief\0e2e.json",
    #     r"H:\code\parttime\glass_screen\data\training_samples\head_region_labelled\test.json",
    # ]
    # crop_ratio_lrtd = [0.93, 0.0, 0.0, 0.0]
    # json_files = [  # ao tu heng dot
    #     r"H:\code\parttime\glass_screen\data\training_samples\fullbodyimages\aohen20180816\hengluo.json",
    #     r"h:\code\parttime\glass_screen\data\training_samples\fullbodyimages\dot-ao20180816\dot-ao20180814.json",
    #     r"H:\code\parttime\glass_screen\data\training_samples\fullbodyimages\dot-tu20180819\test.json",
    #     r"h:\code\parttime\glass_screen\data\training_samples\fullbodyimages\heng-qi20180819\heng-qi20180819.json",
    #     r"h:\code\parttime\glass_screen\data\training_samples\fullbodyimages\huahen20180819\test.json",
    #     r"h:\code\parttime\glass_screen\data\training_samples\fullbodyimages\dotao20180903\test.json",
    #     r"h:\code\parttime\glass_screen\data\training_samples\fullbodyimages\huahen20180903\test.json",
    #     r"h:\code\parttime\glass_screen\data\training_samples\fullbodyimages\huashang20180903\test.json",
    # ]
    # json_files = [  # metal bare
    #     r"h:\code\parttime\glass_screen\data\training_samples\metalbare\debug_metal_output\labelled.json",
    # ]
    #
    # json_files = [  # huashang only
    #     r"h:\code\parttime\glass_screen\data\training_samples\huashang\huashang\label.json",
    # ]
    # json_files = [  # tuheng only
    #     r"h:\code\parttime\glass_screen\data\training_samples\huaheng\ATLhuahenfinish\huahen.json",
    # ]
    # # Three channel samples json_files = [
    # # r"h:\code\parttime\glass_screen\data\training_samples\fullbodyimages3channel-aligned\huashang201810081.1\test
    # # .json", # r"H:\code\parttime\glass_screen\data\training_samples\fullbodyimages3channel\dot_ao201810041.1\test
    # # .json", # r"H:\code\parttime\glass_screen\data\training_samples\fullbodyimages3channel\huahen201810041.1\test
    # # .json", # r"H:\code\parttime\glass_screen\data\training_samples\fullbodyimages3channel\huahen1.1\test.json",
    # # r"H:\code\parttime\glass_screen\data\training_samples\fullbodyimages3channel\heng_qi1.1\heng-qi20180819.json",
    # # r"H:\code\parttime\glass_screen\data\training_samples\fullbodyimages3channel\dot.tu1.1\test.json",
    # # r"H:\code\parttime\glass_screen\data\training_samples\fullbodyimages3channel\aohen1.1\hengluo.json",
    # # r"H:\code\parttime\glass_screen\data\training_samples\fullbodyimages3channel\dot-ao201808161.1\dot-ao20180816
    # # .json", ]
    #
    # crop_ratio_lrtd = [0.0, 0.0, 0.0, 0.0]
    # split_ratio = 0.02
    #
    # # dst_dir = r'H:\code\parttime\glass_screen\data\training_samples\fullbodyimages\body_multilabelled'
    # dst_dir = r'h:\code\parttime\glass_screen\data\training_samples\huaheng\train_imgs'  # Donot need to exist.
    # if not os.path.exists(dst_dir):
    #     os.mkdir(dst_dir)
    # save_train_txt = os.path.join(dst_dir, 'train.txt')
    # save_test_txt = os.path.join(dst_dir, 'test.txt')
    # ftrain = open(save_train_txt, "w")
    # ftest = open(save_test_txt, "w")
    #
    # save_cnt = 0
    # for cur_file in json_files:
    #     save_cnt = generate_sample(cur_file, ftrain, ftest, split_ratio, save_cnt, True,
    #                                crop_ratio_lrtd=crop_ratio_lrtd, save_dir=dst_dir)
    # ftrain.close()
    # ftest.close()
