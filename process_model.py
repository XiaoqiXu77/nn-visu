#coding: utf-8

from __future__ import print_function
import sys
sys.path += ['./layers/', './utils/', './models/']

import numpy as np
from keras.callbacks import EarlyStopping
from keras.preprocessing.image import ImageDataGenerator
from keras.datasets import cifar10
from keras.optimizers import Adam, SGD, RMSprop
from keras.utils import to_categorical
from random import sample
from copy import deepcopy
from print_norm_utils import print_images, plot_kernels, load_input, normalize_input, query_yes_no, resize
from KerasDeconv import DeconvNet
from keras.applications.vgg16 import preprocess_input
import cPickle as pickle
import models
import deconv_models
import argparse
import glob
import cv2
import os
from imagenet1000 import imagenet1000
from cats import dict_labels_cats
from utils import get_deconv_images, plot_deconv, plot_max_activation, find_top9_mean_act
import matplotlib.pyplot as plt

## Training models
# python2.7 process_model.py --tmodel vonc --tdata CIFAR-10 --trun training --trained 0 --epoch 250 --lr 0.01 --optimizer Adam --batch 64
# python2.7 process_model.py --tmodel conv --tdata CIFAR-10 --trun training --trained 0 --epoch 10 --lr 0.0001 --optimizer Adam --batch 128

## CREDIT: Adapted from practicals/HMW2 from Andrea Vedaldi and Andrew Zisserman 
## by Gul Varol and Ignacio Rocco in PyTorch

## Training is performed on training set of CIFAR-10
## Testing is performed either on testing set of CIFAR-10, either on another dataset

##################################################################################
##################################################################################
############# ARGUMENTS

# For reproducibility
np.random.seed(1000)

parser = argparse.ArgumentParser(description='Simple NN models')
parser.add_argument('--tmodel', type=str, default='conv', metavar='M',
                    help='In ["conv2", "conv", "vgg"].')
parser.add_argument('--trun', type=str, default='training', metavar='R',
                    help='In ["training", "testing", "deconv"].')
parser.add_argument('--tdata', type=str, default='CIFAR-10', metavar='D',
                    help='In ["CIFAR-10", "CATS"].')
parser.add_argument('--batch', type=int, default=64, metavar='B',
                    help='Batch size.')
parser.add_argument('--epoch', type=int, default=10, metavar='E',
                    help='Number of epochs.')
parser.add_argument('--optimizer', type=str, default="SGD", metavar='O',
                    help='SGD/Adam optimizers.')
parser.add_argument('--trained', type=int, default=1, metavar='T',
                    help='Import initialized weights: in {0, 1}.')
parser.add_argument('--lr', type=float, default=0.1, metavar='L',
                    help='Learning rate in (0,1).')
parser.add_argument('--decay', type=float, default=1e-6, metavar='C',
                    help='Decay rate in (0,1).')
parser.add_argument('--momentum', type=float, default=0.9, metavar='U',
                    help='Momentum.')
parser.add_argument('--layer', type=str, default="conv1-1", metavar='Y',
                    help='Name of the layer to deconvolve.')
parser.add_argument('--verbose', type=int, default=0, metavar='V',
                    help='Whether to print things or not: in {0, 1}.')
parser.add_argument('--subtask', type=str, default="", metavar='S',
                    help='Sub-task for deconvolution.')
parser.add_argument('--tdeconv', type=str, default="keras", metavar='K',
                    help='Choice of implementation for deconvolution: Mihai Dusmanu\'s (\'custom\') or DeepLearningImplementations (\'keras\').')
parser.add_argument('--loss', type=str, default="categorical_crossentropy", metavar='O',
                    help='Choice of loss function, among those supported by Keras.')
args = parser.parse_args()

folder = "./data/figures/"
if not os.path.exists(folder):
	os.mkdir(folder)

folder += args.tdata + "/"
if not os.path.exists(folder):
	os.mkdir(folder)

if (args.optimizer == "SGD"):
	optimizer = SGD(lr = args.lr, decay=args.decay, momentum=args.momentum, nesterov=True)
if (args.optimizer == "Adam"):
	optimizer = Adam(lr=args.lr, decay=args.decay)
if (args.optimizer == "rmsprop"):
	optimizer = RMSprop(lr=args.lr)

##################################################################################
##################################################################################
############# DATA

# Load data
(X_train, Y_train), (X_test, Y_test) = cifar10.load_data()

## Preprocessing/Size of resized images
def aux_process_input(x, sz, training_means):
	n = np.shape(x)[0]
	images = []
	for i in range(n):
		im = normalize_input(x, sz, training_means)
		im = np.expand_dims(im, axis=0)
		images.append(im)
	x = np.concatenate(images, axis=0)
	return x

if (args.tmodel == "vgg"):
	sz = 224
	preprocess_image = lambda x : preprocess_input(resize(x, (np.shape(x)[0], sz, sz, 3)))/255.
else:
	sz = 32
	training_means = [np.mean(X_train[:,:,i].astype('float32')) for i in range(3)]
	preprocess_image = lambda x : aux_process_input(x, sz, training_means)
	#preprocess_image = lambda x : resize(x, (1, sz, sz, 3))/255. #(np.shape(x)[0], sz, sz, 3)

## CREDIT: Keras training on CIFAR-10 
## https://gist.github.com/giuseppebonaccorso/e77e505fc7b61983f7b42dc1250f31c8

## CREDIT: https://github.com/tdeboissiere/DeepLearningImplementations/tree/master/DeconvNet
if (args.trun != "training" and args.tdata == "CATS"):
	list_img = glob.glob("./data/cats/*.jpg*")
	assert len(list_img) > 0, "Put some images in the ./data/cats folder"
	labels = [dict_labels_cats[img] for img in list_img]
	if len(list_img) < args.batch:
		list_img = (int(args.batch / len(list_img)) + 2) * list_img
		list_img = list_img[:args.batch]
		labels = (int(args.batch / len(labels)) + 2) * labels
		labels = labels[:args.batch]
	data = np.array([load_input(im_name, sz) for im_name in list_img])
	if (len(np.shape(data)) > 4):
		X_test = data.reshape((np.shape(data)[0], np.shape(data)[2], np.shape(data)[3], np.shape(data)[4]))
	else:
		X_test = data
	Y_test = np.array(labels)

if (args.trun != "training" and args.tdata == "CATS"):
	num_classes = 1000
else:
	num_classes = 1000#10

## Preprocessing
## CREDIT: https://keras.io/preprocessing/image/
Y_train_c = to_categorical(Y_train, num_classes)
Y_test_c = to_categorical(Y_test, num_classes)
Y_train_c = Y_train_c.astype('float32')
Y_test_c = Y_test_c.astype('float32')

## Decomment to print 5*nrows random images from X_train
#print_images(X_train, Y_train, num_classes=10, nrows=2)
#print_images(X_test, Y_test, num_classes=num_classes, nrows=2)

## Cut X_train into training and validation datasets
p = 0.30
n = np.shape(X_train)[0]
in_val = sample(range(n), int(p*n))
in_train = list(set(in_val).symmetric_difference(range(n)))
X_val = X_train[in_val, :, :, :]
Y_val = Y_train[in_val]
Y_val_c = Y_train_c[in_val, :]
X_train = X_train[in_train, :, :, :]
Y_train_c = Y_train_c[in_train, :]

##################################################################################
##################################################################################
############# MODELS

d_models = {"conv": models.Conv, "vgg": models.VGG_16, "conv2": models.Conv2, "vonc": models.Vonc}
d_dmodels = {"conv": deconv_models.Conv, "vgg": deconv_models.VGG_16, "conv2": deconv_models.Conv2, "vonc": deconv_models.Vonc}

## NN model
model = d_models[args.tmodel](pretrained=args.trained>0, deconv=args.trun == "deconv", sz=sz)
if (args.trun != "deconv"):
	model.compile(loss=args.loss, optimizer=optimizer, metrics=['accuracy'])

## "Deconvoluted" version of NN models
if (args.tdeconv == "custom" and args.trun == "deconv"):
	deconv_model = d_dmodels[args.tmodel](pretrained=args.trained>0)#, layer=args.layer if (args.trun=="deconv") else None)
	#deconv_model.compile(loss=args.loss, optimizer=optimizer, metrics=['accuracy'])
if (args.tdeconv == "keras" and args.trun == "deconv"):
	## Or the implementation of DeconvNet in Keras
	deconv_model = DeconvNet(model)

## Print kernels in a given layer
layers = [layer.name for layer in model.layers]
if (args.verbose == 1):
	print("Layer names for model " + args.tmodel + ":")
	print(layers)
	print("______________________\nSummary:")
	print(model.summary())

#layer = layers[1]
#print("Plotting kernel from layer \'" + layer + "\'")
#plot_kernels(model, layer)

###########################################
## TRAINING/TESTING/DECONV PIPELINES     ##
###########################################

def run_nn(datagen, X, Y_c, Y, batch_size, training=False, verbose=True, kmin=10):
	datagen.fit(X)
	labels = []
	n = np.shape(X)[0]
	epochs = args.epoch if (training) else 1
	for e in range(epochs):
		batch = 0
		print('Epoch', e+1)
		for x_batch, y_batch in datagen.flow(X, Y_c, batch_size=batch_size):
			print("Batch #" + str(batch+1) + "/" + str(n/batch_size+1))
			if (training):
				hist = model.fit(x_batch, y_batch, verbose=1,
					epochs=1,shuffle=True,
					callbacks=[EarlyStopping(monitor="loss", min_delta=0.001, patience=3)])
			else:
				predictions = model.predict(x_batch, batch_size, verbose=1)
				try:
					pred_ = [np.argmax(predictions[0][i, :]) for i in range(len(predictions))]
				except:
					pred_ = [np.argmax(predictions[i, :]) for i in range(len(predictions))]
				labels += pred_
				Y_batch = np.array([np.argmax(y_batch[i, :]) for i in range(len(predictions))])
				acc = np.array(pred_)==Y_batch
				acc = np.sum(acc)/float(len(predictions))
				print(str(batch_size*(batch+1)) + "/" + str(n) + ": acc = " + str(acc))
			if batch >= n / batch_size:
				break
			else:
				batch += 1
	if (not training):
		labels = np.array(labels)
		if (verbose):
			acc = np.sum(labels == Y)/float(n)
			if (args.verbose):
				print(model.summary())
			k = min(np.shape(labels)[0], kmin)
			pred = [imagenet1000[labels[i]] for i in range(np.shape(labels)[0])]
			if (args.tdata == "CATS"):
				real = [imagenet1000[i] for i in Y[:k].T.tolist()]
			else:
				real = [imagenet1000[i] for i in Y[:k].T[0].tolist()]
			print("")
			print("PREDICTED" + "\t"*4 + "REAL LABELS")
			for i in range(k):
				print(pred[i] + "\t\t" + real[i])
			print('')
			print('* ACCURACY %.2f' % acc)
		return labels
	if (verbose):
		acc = hist.history["acc"][-1]
		loss = hist.history["loss"][-1]
		print("ACCURACY\t%.3f" % (acc))
		print("LOSS\t\t%.3f" % (loss))
	if (query_yes_no("Save weights?", default="yes")):
		model.save_weights('./data/weights/'+args.tmodel+'_weights.h5')
	return hist

def process_fmap(out, im, layer="", sz=sz):
	layer = "_"+layer
	out = np.resize(out, (sz, sz, 3))
	plt.subplot('121')
	plt.imshow(out)
	plt.axis('off')
	plt.xlabel("Feature map for layer " + layer[1:])
	values = list(map(lambda x : str(round(x, 1)), list(map(lambda f : f(out), [np.mean, np.std, np.median]))))
	plt.title("Mean = " + values[0] + " STD = " + values[1] + " Median = " + values[2])
	plt.subplot('122')
	plt.imshow(np.resize(im, (sz, sz, 3)))
	plt.axis('off')
	plt.xlabel("Input image")
	plt.show()
	if (query_yes_no("Save feature map?", default="yes")):
		plt.savefig(out, "feature_map_layer" + layer + ".png", bbox="tight")

## Generator for training data
datagen_train = ImageDataGenerator(
	rescale=1.,
	featurewise_center=False,
	featurewise_std_normalization=False,
	## Normalization
	preprocessing_function=preprocess_image,
	## Data augmentation
	rotation_range=20,
	width_shift_range=0.2,
	height_shift_range=0.2,
	horizontal_flip=True,
	data_format="channels_last",
)

## Generator for testing data
datagen_test = ImageDataGenerator(
	rescale=1.,
	featurewise_center=False,
	featurewise_std_normalization=False,
	## Normalization
	data_format="channels_last",
	preprocessing_function=preprocess_image,
)

if (args.trun == "training"):
	hist = run_nn(datagen_train, X_train, Y_train_c, Y_train, args.batch, training=True, verbose=True)
	labels = run_nn(datagen_train, X_val, Y_val_c, Y_val, args.batch, training=False, verbose=True)
if (args.trun == "testing"):
	k = min(1000, np.shape(X_test)[0])
	X_test = X_test[:k, :, :, :]
	Y_test_c = Y_test_c[:k, :]
	Y_test = Y_test[:k]
	labels = run_nn(datagen_test, X_test, Y_test_c, Y_test, args.batch, training=False, verbose=True)
if (args.trun == "deconv"):
	forward_net = models.Conv(pretrained=True, deconv=True)
	backward_net = deconv_models.Conv(pretrained=True)
	im = normalize_input("./data/cats/cat1.jpg", sz)
	out = forward_net.predict([im])
	print(len(out))
	print(list(map(np.shape, out)))
	out = backward_net.predict(out)
	#im = preprocess_image(X_test[0, :, :, :])
	#plt.imshow(np.resize(im, np.shape(im)[1:]))
	#plt.show()
	#out = model.predict([im])
	#print(len(out))
	#print(list(map(np.shape, out)))
	#out = deconv_model.predict(out)
	process_fmap(out, im)
	raise ValueError
	if (args.tdeconv == "keras"):
		layer_name = layers[-2]
		i = 0
		print("* Target layer: \'" + layer_name + "\' and image #" + str(i+1))
		out = deconv_model.get_deconv(np.reshape(X_test[i, ::], (1, sz, sz, 3)), layer_name) # target_layer
	else:
		layer_name = layers[-2]
		out = deconv_model.predict(out) # layer=layer_name
	plt.figure(figsize=(20, 20))
	plt.imshow(out)
	plt.show()
	raise ValueError
	## Save output feature map
	#If you want to reconstruct from a single feature map / activation, you can
	# simply set all the others to 0. (in file "models/deconv_models.py")
	plt.savefig(folder + "fmap_" + str(i) + ".png", bbox_inches="tight")
	if (args.subtask == "max_activation"):
		get_max_act = True
		if get_max_act:
			if not model:
				model = load_model('./Data/vgg16_weights.h5')
			if not Dec:
				Dec = KerasDeconv.DeconvNet(model)
		d_act_path = './Data/dict_top9_mean_act.pickle'
		d_act = {"convolution2d_13": {},
			 "convolution2d_10": {}
			 }
		for feat_map in range(10):
			d_act["convolution2d_13"][feat_map] = find_top9_mean_act(
				data, Dec, "convolution2d_13", feat_map, batch_size=32)
			d_act["convolution2d_10"][feat_map] = find_top9_mean_act(
				data, Dec, "convolution2d_10", feat_map, batch_size=32)
			with open(d_act_path, 'w') as f:
				pickle.dump(d_act, f)


###################################################################
###################################################################

#bow_comparison(fmap, images_list, list_img=list_img)
#corresp_comparison(fmap, images_list, list_img=list_img)
#repeatability_harris(fmap, images_list, list_img=list_img)

    ###############################################
    # Action 1) Get max activation for a secp ~/deconv_specificlection of feat maps
    ###############################################


    ###############################################
    # Action 2) Get deconv images of images that maximally activate
    # the feat maps selected in the step above
    ###############################################
#    deconv_img = True
#    if deconv_img:
#        d_act_path = './Data/dict_top9_mean_act.pickle'
#        d_deconv_path = './Data/dict_top9_deconv.pickle'
#        if not model:
#            model = load_model('./Data/vgg16_weights.h5')
#        if not Dec:
#            Dec = KerasDeconv.DeconvNet(model)
#        get_deconv_images(d_act_path, d_deconv_path, data, Dec)

    ###############################################
    # Action 3) Get deconv images of images that maximally activate
    # the feat maps selected in the step above
    ###############################################
#    plot_deconv_img = True
#    if plot_deconv_img:
#        d_act_path = './Data/dict_top9_mean_act.pickle'
#        d_deconv_path = './Data/dict_top9_deconv.npz'
#        target_layer = "convolution2d_10"
#        plot_max_activation(d_act_path, d_deconv_path,
#                            data, target_layer, save=True)
#
    ###############################################
    # Action 4) Get deconv images of some images for some
    # feat map
    ###############################################
#    deconv_specific = False
#    img_choice = False  # for debugging purposes
#    if deconv_specific:
#        if not model:
#            model = load_model('./Data/vgg16_weights.h5')
#        if not Dec:
#            Dec = KerasDeconv.DeconvNet(model)
#        target_layer = "convolution2d_13"
#        feat_map = 12
#        num_img = 25
#        if img_choice:
#            img_index = []
#            assert(len(img_index) == num_img)
#        else:
#            img_index = np.random.choice(data.shape[0], num_img, replace=False)
#        plot_deconv(img_index, data, Dec, target_layer, feat_map)
