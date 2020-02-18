import cv2
import numpy as np
from matplotlib import pyplot as plt
from os import listdir
from os.path import isfile, join
import random
from matplotlib.gridspec import GridSpec

def show_MSER_blobs(img, blobs):
    canvas1 = img.copy()
    canvas3 = np.zeros_like(img)
    for cnt in blobs:
        # Show in separate image
        xx = cnt[:,0]
        yy = cnt[:,1]
        color = [random.randint(0, 255) for _ in range(3)]
        canvas3[yy, xx] = color

        # Show as BBox
        # get the min area rect
        rect = cv2.minAreaRect(cnt)
        box = cv2.boxPoints(rect)
        # convert all coordinates floating point values to int
        box = np.int0(box)
        # draw a red 'nghien' rectangle
        canvas1 = cv2.drawContours(canvas1, [box], 0, (0, 255, 0), 1)

    ## Show
    plt.subplot(121)
    show_image(canvas1)
    plt.subplot(122)
    show_image(canvas3)

# Extracts the image patch given the keypoint
def patch_from_keypoint(img, keypoint):
    patch_center = np.array(keypoint.pt).astype(np.int)
    patch_size = int(keypoint.size/1.5)
    angle = keypoint.angle

    # Extracting large patch around center
    patch_x = int(patch_center[1] - patch_size)
    patch_y = int(patch_center[0] - patch_size)
    x0 = np.amax([0,patch_x])
    y0 = np.amax([0,patch_y])
    x1 = np.amin([img.shape[0],patch_x+2*patch_size])
    y1 = np.amin([img.shape[1],patch_y+2*patch_size])
    patch_image = img[x0:x1,y0:y1]
    
    # Rotating patch and cropping (This does nothing without SIFT)
    rows,cols,_ = patch_image.shape
    M = cv2.getRotationMatrix2D((cols/2,rows/2),angle,1)
    patch_image = cv2.warpAffine(patch_image,M,(cols,rows))
    return patch_image

# Shows N descriptors taken at random
def show_random_descriptors(img, keypoints, descriptors, N = 5):
    # Getting random keypoints 
    random_idx = [random.randint(0,len(keypoints)-1) for n in range(N)]
    some_keypoints = [keypoints[i] for i in random_idx] 
    some_descriptors = [descriptors[i] for i in random_idx]
    
    # Setting up axes
    fig = plt.figure(constrained_layout=True,figsize=(15,8))
    gs = GridSpec(N, 8, figure=fig)
    
    # Showing the image with the keypoints
    img_with_kpts = cv2.drawKeypoints(img, some_keypoints, None,color=[255,0,0], 
                       flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
    ax1 = fig.add_subplot(gs[:, :-2])
    ax1.set_title("Image")
    show_image(img_with_kpts)
    
    # Showing the patched with their desctiptors
    for n in range(N):
        # Getting and showing patch
        patch = patch_from_keypoint(img, some_keypoints[n])
        ax = fig.add_subplot(gs[n, -2])
        if n == 0:
            ax.set_title("Patch")
        show_image(patch)
        
        # Getting descriptor and plotting it
        ax = fig.add_subplot(gs[n, -1])
        if n == 0:
            ax.set_title("Descriptor")
        x = np.arange(len(some_descriptors[n]))
        plt.bar(x,some_descriptors[n])

class Dataset():
    def __init__(self, folder="jpg"):
        self.path = 'data/' + folder
        self.all_images = [f for f in listdir(self.path) if isfile(join(self.path, f))]
    
    def print_files(self):
        print(self.all_images[:5])
        
    def get_image_by_name(self, image_name=None, gray=True):
        image = cv2.imread(self.path + '/' + image_name)
        image = cv2.resize(image, (0,0), fx=0.3, fy=0.3) 
        if gray:
            gray = cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
            return np.float32(gray)
        else:
            return cv2.cvtColor(image,cv2.COLOR_BGR2RGB)
    
    def get_random_image(self, gray=False):
        return self.get_image_by_name(random.choice(self.all_images),gray)

def show_image(img, gray=False, image_size=6):
    if not gray:
        plt.imshow(img,aspect="equal")
    else:
        plt.imshow(img,aspect="equal", cmap="gray")
    
def show_corners_on_image(img, corners):
    img_3channels = cv2.cvtColor(img/255,cv2.COLOR_GRAY2RGB)
    img_3channels[corners]=[1,0,0]
    show_image(img_3channels)

## Read image and change the color space
def detect_MSER_blobs(img, min_area=4000, max_area=200000):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    ## Get mser, and set parameters
    mser = cv2.MSER_create(_max_variation = 0.5)
    mser.setMinArea(min_area)
    mser.setMaxArea(max_area)
    
    ## Do mser detection, get the coodinates and bboxes
    coordinates, bboxes = mser.detectRegions(gray)

    ## Filter the coordinates
    vis = img.copy()
    coords = []
    for coord in coordinates:
        bbox = cv2.boundingRect(coord)
        x,y,w,h = bbox
        if w< 20 or h < 20 or w/h > 5 or h/w > 5:
            continue
        coords.append(coord)
    return coords