#coding:utf-8

import matplotlib.pyplot as plt
import numpy as np
from torchvision.utils import make_grid
import torch
import cv2
from imagenet1000 import imagenet1000

## CREDIT: https://blog.plon.io/tutorials/cifar-10-classification-using-keras-tutorial/
# functions to show 5*nrows random images from set X with labels Y (CIFAR-10: 10 classes)
def print_images(X, Y, num_classes=10, nrows=2):
	fig = plt.figure(figsize=(10,3))
	## For CIFAR-10
	if (num_classes == 10):
		class_names = ['plane', 'car', 'bird', 'cat', 'deer', 'dog', 'frog', 'horse', 'ship', 'truck']
	## For ImageNet
	elif (num_classes == 1000):
		class_names = imagenet1000.values()
	tick = 0
	for i in range(num_classes):
		idx = np.where(Y[:]==i)[0]
		if (len(idx) == 0):
			continue
		ax = fig.add_subplot(nrows, 5, 1 + tick, xticks=[], yticks=[])
		tick += 1
		features_idx = X[idx,::]
		img_num = np.random.randint(features_idx.shape[0])
		im = features_idx[img_num,::]
		ax.set_title(class_names[i])
		plt.imshow(im)
	plt.show()

# Code adapted from https://github.com/pedrodiamel/nettutorial/blob/master/pytorch/pytorch_visualization.ipynb
## Visualize feature maps/kernels from layer
def vistensor(layer, layer_name, ch=0, allkernels=False, nrow=20, padding=1):
	layer = torch.from_numpy(layer).float()
	n,c,w,h = layer.shape
	if allkernels: layer = layer.view(n*c,-1,w,h)
	elif c != 3: layer = layer[:,ch,:,:].unsqueeze(dim=1) 
	rows = np.min( (layer.shape[0]//nrow + 1, 64 )  )    
	grid = make_grid(layer, nrow=nrow, normalize=True, padding=padding)
	plt.figure( figsize=(nrow,rows) )
	plt.title("\nVisualization of tensor \'" + layer_name + "\'")
	plt.imshow(grid.numpy().transpose((1, 2, 0)))
	plt.show()

def plot_kernels(model, layer_name):
	layer = model.get_layer(layer_name).get_weights()
	if (len(layer) == 0):
		print("Layer \'" + layer_name + "\' has no weights! See model summary below")
		print(model.summary())
		raise ValueError
	vistensor(layer[0], layer_name)

def load_input(im_name, sz):
	im = cv2.imread(im_name)
	im = cv2.resize(im, (sz, sz)).astype(np.float32)
	im = np.expand_dims(im, axis=0)
	im /= 255.
	return im

def normalize_input(im, sz, training_means=[103.939, 116.779, 123.68], data_format="channels_last"):
	if (str(type(im)) == "<type \'str\'>"):
		im = load_input(im, sz)
	im = cv2.resize(im, (sz, sz)).astype(np.float32)
	## zero mean on each channel across the training dataset
	if (np.max(im) <= 1):
		im *= 255.
	for i in range(len(training_means)):
		if (data_format == "channels_last"):
			im[:, :, :, i] -= training_means[i]
		else:
			im[:, i, :, :] -= training_means[i]
	## 0-1 normalization
	if (np.max(im) > 1):
		im /= 255.
	## standardization
	#im = (im-np.mean(im))/np.std(im)
	im = im-np.min(im)
	im /= np.max(im)
	return im
