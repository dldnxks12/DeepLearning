############# Used Method ##############

# Camera Calibration
# Side Walk Segmentation 
# Remove noise with Morpholgy - Opening
# Get Contours and select biggest Area Contour
# HoughLinesP
# Get Main Left / Right Line
# Get ROI 
# Interpolation
# Line Moving Average
# Get Angle    + moving average + remove outliar
# Get Distance + moving average + remove outliar
# Control Output
# Communication related work 

#### Remove ####

	# Canny Edge
	# Bird-eye-view

########################################

import os   # Terminal Control
import sys  # Terminal Control 
import cv2
import math
import time
import pickle
import logging    # For Logger
import subprocess # For parallel Processing 
import numpy as np
import tensorflow as tf
import pyrealsense2 as rs
from model.pspunet import pspunet
from data_loader.display import create_mask

# Get Robot Position (Area = 1/2 * width * height)
def cal_dist(x1, y1, x2, y2, centerX, centerY): 
	Triangle_Area = abs( (x1-centerX)*(y2-centerY) - (y1-centerY)*(x2-centerX) )
	line_distance = math.dist((x1,y1), (x2, y2))
	distance = (2*Triangle_Area) / line_distance 
	return distance

# Get Angle
def get_angle(Points):
	angle = (np.arctan2(Points[1] - Points[3], Points[0] - Points[2]) * 180) / np.pi 	
	return angle

# Get ROI
def ROI(img, vertices, color3 = (255, 255, 255), color1 = 255):
	mask = np.zeros_like(img)
	if len(img.shape) > 2: # 3 channel image
		color = color3
	else:
		color = color1
        	
	cv2.fillPoly(mask, vertices, color)
	ROI_IMG = cv2.bitwise_and(img, mask)
	return ROI_IMG

# Get Main line
def get_fitline(img, f_lines): # 대표선 구하기   
    lines = np.squeeze(f_lines, 1)
    lines = lines.reshape(lines.shape[0]*2,2)
    rows,cols = img.shape[:2]
    output = cv2.fitLine(lines,cv2.DIST_L2,0, 0.01, 0.01)
    vx, vy, x, y = output[0], output[1], output[2], output[3]
    x1, y1 = int(((img.shape[0]-1)-y)/vy*vx + x) , img.shape[0]-1
    x2, y2 = int(((img.shape[0]/2+100)-y)/vy*vx + x) , int(img.shape[0]/2+100)
    
    result = [x1,y1,x2,y2]
    return result

# Init flags and buffers 
def init_var():
	L_x1                     = [] 
	L_y1                     = [] 
	L_x2                     = [] 
	L_y2                     = [] 
	R_x1                     = [] 
	R_y1                     = [] 
	R_x2                     = [] 
	R_y2                     = [] 
	Left_pos_temp            = []   
	Left_angle_temp          = []   
	Right_pos_temp           = []   
	Right_angle_temp         = []    	
	Left_Avg_points_temp     = 0
	Right_Avg_points_temp    = 0

	No_line_flag             = 0
	Left_line_interpolation  = 0
	Right_line_interpolation = 0
	No_line_flag             = 0
	Left_Pos_flag            = 0
	Left_Angle_flag          = 0 
	Right_Pos_flag           = 0  
	Right_Angle_flag         = 0 
	Left_Avg_Pos             = 0        
	Left_Avg_Ang             = 0        
	Right_Avg_Pos            = 0        
	Right_Avg_Ang            = 0      

# GPU Setting
gpus = tf.config.experimental.list_physical_devices('GPU')
if gpus:
    try:
        tf.config.experimental.set_virtual_device_configuration(
       gpus[0],
        [tf.config.experimental.VirtualDeviceConfiguration(memory_limit=500)])
    except RuntimeError as e:
        print(e)

# Configure depth and color streams
pipeline = rs.pipeline()
config = rs.config()

# Get device product line for setting a supporting resolution
pipeline_wrapper = rs.pipeline_wrapper(pipeline)
pipeline_profile = config.resolve(pipeline_wrapper)
device = pipeline_profile.get_device()
device_product_line = str(device.get_info(rs.camera_info.product_line))

found_rgb = False
for s in device.sensors:
    if s.get_info(rs.camera_info.name) == 'RGB Camera':
        found_rgb = True
        break
if not found_rgb:
    exit(0)

config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)

if device_product_line == 'L500':
    config.enable_stream(rs.stream.color, 960, 540, rs.format.bgr8, 30)
else:
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

# Start streaming
pipeline.start(config)

IMG_WIDTH  = 480
IMG_HEIGHT = 272
n_classes  = 7

# Camera Parameters
obj_file   = open("objpoints.pkl", "rb")
img_file   = open("imgpoints.pkl", "rb")
rvecs_file = open("rvecs.pkl", "rb")
tvecs_file = open("tvecs.pkl", "rb")
objpoints = pickle.load(obj_file)
imgpoints = pickle.load(img_file)

ret = 3.2668594862688822
dist = np.load("dist_file.npy")
mtx = np.load("mtx_file.npy")
rvecs = pickle.load(rvecs_file)
tvecs = pickle.load(tvecs_file)

obj_file.close()
img_file.close()
rvecs_file.close()
tvecs_file.close()


# Load trained Model
model = pspunet((IMG_HEIGHT, IMG_WIDTH ,3), n_classes)
model.load_weights("pspunet_weight.h5")

# Logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(message)s')
file_handler = logging.FileHandler('log.txt', mode = 'w')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


# ----  Global Vars ---- #
# Temps
L_x1 = [] # Points temp
L_y1 = [] # Points temp
L_x2 = [] # Points temp
L_y2 = [] # Points temp
R_x1 = [] # Points temp
R_y1 = [] # Points temp
R_x2 = [] # Points temp
R_y2 = [] # Points temp
Left_Avg_points_temp  = 0
Right_Avg_points_temp = 0

# Angle
Base_angle       = 90
Left_Base_angle  = 110 
Right_Base_angle = 80
Left_Angle       = 90
Right_Angle      = 90
Reference_angle  = 0 

# Position
Base_left_distance  = 150  # Init Left Position
Base_right_distance = 150  # Init Right Position 
Left_distance       = 0   # Current Pos 
Right_distance      = 0   # Current Pos 

# Control
Left_direction   = 1
Right_direction  = 1
Left_Difference  = 0 
Right_Difference = 0
Base_weight      = 100
Left_Wheel       = 0
Right_Wheel      = 0
Send_Left_Wheel  = ""
Send_Right_Wheel = ""

# Flags
Camera_init              = False
Init_distance            = True
Left_line_interpolation  = 0
Right_line_interpolation = 0
No_line_flag             = 0
No_left_line_flag        = 0
No_right_line_flag       = 0
Left_Pos_flag            = 0
Left_Angle_flag          = 0 
Right_Pos_flag           = 0  
Right_Angle_flag         = 0 

# Moving Average
Left_pos_temp     = []    # List for Position Moving Average
Left_angle_temp   = []    # List for Angle Moving Average
Right_pos_temp    = []    # List for Position Moving Average
Right_angle_temp  = []    # List for Angle Moving Average
Left_Avg_Pos      = 0     # Average Position
Left_Avg_Ang      = 0     # Average Angle
Right_Avg_Pos     = 0     # Average Position
Right_Avg_Ang     = 0     # Average Angle

# Middle Points 
STM_Weight_Value = 0.7
STM_Ratio        = 20 
Road_line        = 0
Zero_gap         = 0 
Left_check       = 0
Right_check      = 0

# Stop bit 
Stop_bit         = 0

# Log variable
p = 0 

# wait variable
w = 0 

test_img = cv2.imread("test.png")

try:
	while True:		
		p += 1
		h, w = test_img.shape[:2]
		frames = pipeline.wait_for_frames()
		color_frame = frames.get_color_frame()
		if not color_frame:
		  continue

		# Convert images to numpy arrays
		color_image = np.asanyarray(color_frame.get_data())

		# Camera Adaptataion 
		if w > 10:
			Camera_init = True

		if Camera_init == False:			
			w += 1
			cv2.imshow("Color", color_image)
			cv2.waitKey(1)
			continue

		# ----------------- Calibration ---------------------- #
		newcameramtx , roi = cv2.getOptimalNewCameraMatrix(mtx, dist, (w, h), 1, (w, h))
		color_image = cv2.undistort(color_image, mtx, dist, None, newcameramtx)
		x, y, w, h = roi
		color_image = color_image[y:y+h , x:x+w]
		# ---------------------------------------------------- #
		
		# ------------------- Segmentation ------------------- #
		frame = cv2.resize(color_image, (IMG_WIDTH, IMG_HEIGHT))
		frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
		frame = frame[tf.newaxis, ...]
		frame = frame / 255
		pre   = model.predict(frame)
		pre   = create_mask(pre).numpy()

		frame2 = frame/2
		frame2[0] *= 0
		frame2[0][(pre==6).all(axis=2)] += [1.0, 1.0, 1.0]		
		# ---------------------------------------------------- #

		video          =  np.uint8(frame2 * 255)		
		dst            =  video[0].copy()
		canvas         =  dst.copy() * 0
		canvas2        =  dst.copy() * 0
		canvas3        =  dst.copy() * 0
		canvas_height, canvas_width = canvas.shape[:2]
				
		gray           =  cv2.cvtColor(dst, cv2.COLOR_BGR2GRAY)
				
		# Make ROI
		height, width  = gray.shape[:2]
		#vertices = np.array([[(0,height),(width/2-120, height/2 - 30), (width/2+120, height/2 - 30), (width,height)]], dtype=np.int32)  		
		vertices = np.array([[(0,height),(0, height/2 - 30), (width, height/2 - 30), (width,height)]], dtype=np.int32)  		
		ROI_IMG = ROI(gray, vertices)

		# Remove small noise 
		k          = cv2.getStructuringElement(cv2.MORPH_RECT, (5,5))
		opening    = cv2.morphologyEx(ROI_IMG, cv2.MORPH_OPEN, k)      # Opening for ROI Image 

		_, opening = cv2.threshold(opening, 127, 255, cv2.THRESH_BINARY)

		# Get Contour of ROI Image (draw external contour only)
		contours, hierachy = cv2.findContours(opening, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
		if len(contours) > 0 :
			max_cntr = contours[0]
			max_area = cv2.contourArea(max_cntr)
			for i in contours:				
				if max_area < cv2.contourArea(i):
					max_area =  cv2.contourArea(i)
					max_cntr = i

			# Get hull convex Contours
			hull = cv2.convexHull(max_cntr)
			cv2.drawContours(canvas3, [hull], -1, (255, 255, 255), 1)

		cv2.imshow("Opening", opening)
		cv2.imshow("Contour", canvas3)

		Input_img  = cv2.cvtColor(canvas3, cv2.COLOR_BGR2GRAY)
		lines      = cv2.HoughLinesP(Input_img, 1, np.pi/180, 50, None, 30, 20)	  
			
		# ------------------------ Initialize distance ---------------------- #	
		if (lines is not None) and (Init_distance == True): 			

			# Camera Adaptataion 2													
			No_line_flag = 0 			

			# Eliminate axis 1
			lines2 = np.squeeze(lines, 1)
			slope_degree = (np.arctan2(lines2[:,1] - lines2[:,3], lines2[:,0] - lines2[:,2]) * 180) / np.pi

			lines2 = lines2[np.abs(slope_degree) < 150]
			slope_degree = slope_degree[np.abs(slope_degree) < 150]			
			lines2 = lines2[np.abs(slope_degree) > 30]
			slope_degree = slope_degree[np.abs(slope_degree) > 30]
									
			L_lines = lines2[(slope_degree) > 0, :]			
			R_lines = lines2[(slope_degree) < 0, :]

			# Restore axis 1
			L_lines = L_lines[:,None]
			R_lines = R_lines[:,None]					
		
			# Only when 2 lines appears ... 
			if (len(L_lines) > 0) and (len(R_lines) > 0):

				# LEFT #################################		
				left_fit_line  = get_fitline(ROI_IMG, L_lines)
				
				if len(L_x1) < 3:
					L_x1.append(left_fit_line[0])
					L_y1.append(left_fit_line[1])
					L_x2.append(left_fit_line[2])
					L_y2.append(left_fit_line[3])
					x1 = int(sum(L_x1) / len(L_x1))
					y1 = int(sum(L_y1) / len(L_y1))
					x2 = int(sum(L_x2) / len(L_x2)) 
					y2 = int(sum(L_y2) / len(L_y2)) 
					Left_Avg_points_temp = [x1, y1, x2, y2]

				else:
					L_x1.append(left_fit_line[0])
					L_y1.append(left_fit_line[1])
					L_x2.append(left_fit_line[2])
					L_y2.append(left_fit_line[3])

					x1 = int(sum(L_x1[-3:]) / 3)
					y1 = int(sum(L_y1[-3:]) / 3)
					x2 = int(sum(L_x2[-3:]) / 3)
					y2 = int(sum(L_y2[-3:]) / 3)
					Left_Avg_points_temp = [x1, y1, x2, y2]

				cv2.line(canvas, (x1, y1), (x2, y2), (255,255,255), 2)					
				
				# Distance Moving Average + remove outliar 
				Left_distance  = cal_dist(x1, y1, x2, y2, width//2, height)
				if len(Left_pos_temp) <= 3: 
					if len(Left_pos_temp) < 2:
						Left_pos_temp.append(Left_distance) 
					else:
						if (abs(Left_pos_temp[-1] - Left_distance) > 50) and Left_Pos_flag < 3:
							Left_Pos_flag += 1
						else:
							Left_Pos_flag = 0 
							Left_pos_temp.append(Left_distance)
					Left_Avg_Pos = np.mean(Left_pos_temp)		

				else:
					if(abs(Left_pos_temp[-1] - Left_distance) > 50) and Left_Pos_flag < 3:
						Left_Pos_flag += 1
					else:
						Left_Pos_flag = 0 
						Left_pos_temp.append(Left_distance)
					Left_Avg_Pos = np.mean(Left_pos_temp[-3:])				

				# RIGHT ################################
				right_fit_line  = get_fitline(ROI_IMG, R_lines)

				if len(R_x1) < 3:
					R_x1.append(right_fit_line[0])
					R_y1.append(right_fit_line[1])
					R_x2.append(right_fit_line[2])
					R_y2.append(right_fit_line[3])
					x1 = int(sum(R_x1) / len(R_x1))
					y1 = int(sum(R_y1) / len(R_y1)) 
					x2 = int(sum(R_x2) / len(R_x2))
					y2 = int(sum(R_y2) / len(R_y2)) 
					Right_Avg_points_temp = [x1, y1, x2, y2]

				else:
					R_x1.append(right_fit_line[0])
					R_y1.append(right_fit_line[1])
					R_x2.append(right_fit_line[2])
					R_y2.append(right_fit_line[3])

					x1 = int(sum(R_x1[-3:]) / 3)
					y1 = int(sum(R_y1[-3:]) / 3)
					x2 = int(sum(R_x2[-3:]) / 3)
					y2 = int(sum(R_y2[-3:]) / 3)
					Right_Avg_points_temp = [x1, y1, x2, y2]

				cv2.line(canvas, (x1, y1), (x2, y2), (255,255,255), 2)					

				# Distance Moving Average + remove outliar 
				Right_distance = cal_dist(x1, y1, x2, y2, width // 2, height)
				if len(Right_pos_temp) <= 3: 
					if len(Right_pos_temp) < 2:
						Right_pos_temp.append(Right_distance) 
					else:
						if (abs(Right_pos_temp[-1] - Right_distance) > 50) and Right_Pos_flag < 3:
							Right_Pos_flag += 1
						else:
							Right_Pos_flag = 0 
							Right_pos_temp.append(Right_distance)
					Right_Avg_Pos = np.mean(Right_pos_temp)						
				else:
					if(abs(Right_pos_temp[-1] - Right_distance) > 50) and Right_Pos_flag < 3:
						Right_Pos_flag += 1
					else:
						Right_Pos_flag = 0 
						Right_pos_temp.append(Right_distance)
					Right_Avg_Pos = np.mean(Right_pos_temp[-3:])
											
				STM_Left_Dist  = Left_Avg_Pos   
				STM_Right_Dist = Right_Avg_Pos  

				# if Gap + : Left, Gap - : Right ee
				STM_Gap = ((STM_Right_Dist - STM_Left_Dist) / (STM_Right_Dist + STM_Left_Dist)) * 100 
				STM_Gap = (STM_Gap * STM_Weight_Value) + STM_Ratio

				if abs(STM_Gap) > 50:
					if STM_Gap > 0:
						STM_Gap = 50
					else:
						STM_Gap = -50
						
				if STM_Gap < 0: # Road line is on the right side of middle line
					Left_Wheel      = 100 + STM_Gap
					Right_Wheel     = 100 - STM_Gap
					Left_direction  = 1
					Right_direction = 1

				else:           # Road line is on the left side of middle line
					Left_Wheel      = 100 + STM_Gap
					Right_Wheel     = 100 - STM_Gap
					Left_direction  = 1
					Right_direction = 1

				cv2.line(canvas2, (canvas_width//2 + int((STM_Gap / STM_Weight_Value)*2), canvas_height), \
				(canvas_width//2 + int((STM_Gap / STM_Weight_Value)*2), canvas_height // 2), (255, 255, 255), 2, cv2.LINE_AA) 
		
				if abs(STM_Gap) < 30:
					print(f"Zero Gap || STM_Gap : {STM_Gap}")								
					Zero_gap += 1
					if Zero_gap > 3:
						# Replace left / right base distance
						Base_left_distance  = Left_Avg_Pos
						Base_right_distance = Right_Avg_Pos
						Init_distance = False 
						print("INIT Distance END")						
				else:
					Zero_gap = 0 

			elif len(L_lines) > 0 and len(R_lines) == 0:		
				left_fit_line  = get_fitline(ROI_IMG, L_lines)
				
				if len(L_x1) < 3:
					L_x1.append(left_fit_line[0])
					L_y1.append(left_fit_line[1])
					L_x2.append(left_fit_line[2])
					L_y2.append(left_fit_line[3])
					x1 = int(sum(L_x1) / len(L_x1))
					y1 = int(sum(L_y1) / len(L_y1))
					x2 = int(sum(L_x2) / len(L_x2)) 
					y2 = int(sum(L_y2) / len(L_y2)) 
					Left_Avg_points_temp = [x1, y1, x2, y2]

				else:
					L_x1.append(left_fit_line[0])
					L_y1.append(left_fit_line[1])
					L_x2.append(left_fit_line[2])
					L_y2.append(left_fit_line[3])

					x1 = int(sum(L_x1[-3:]) / 3)
					y1 = int(sum(L_y1[-3:]) / 3)
					x2 = int(sum(L_x2[-3:]) / 3)
					y2 = int(sum(L_y2[-3:]) / 3)
					Left_Avg_points_temp = [x1, y1, x2, y2]

				cv2.line(canvas, (x1, y1), (x2, y2), (255,255,255), 2)					
				
				# Distance Moving Average + remove outliar 
				Left_distance  = cal_dist(x1, y1, x2, y2, width//2, height)
				if len(Left_pos_temp) <= 3: 
					if len(Left_pos_temp) < 2:
						Left_pos_temp.append(Left_distance) 
					else:
						if (abs(Left_pos_temp[-1] - Left_distance) > 50) and Left_Pos_flag < 3:
							Left_Pos_flag += 1
						else:
							Left_Pos_flag = 0 
							Left_pos_temp.append(Left_distance)
					Left_Avg_Pos = np.mean(Left_pos_temp)		

				else:
					if(abs(Left_pos_temp[-1] - Left_distance) > 50) and Left_Pos_flag < 3:
						Left_Pos_flag += 1
					else:
						Left_Pos_flag = 0 
						Left_pos_temp.append(Left_distance) 
					Left_Avg_Pos = np.mean(Left_pos_temp[-3:])				

					STM_Left_Dist 	= Left_Avg_Pos
					STM_Gap = ((Base_left_distance - STM_Left_Dist) / (Base_left_distance + Base_right_distance)) * 100 * 2
					STM_Gap = (STM_Gap * STM_Weight_Value) + STM_Ratio

					if abs(STM_Gap) > 50:
						if STM_Gap > 0:
							STM_Gap = 50
						else:
							STM_Gap = -50

					if STM_Gap < 0: 
						Left_Wheel      = 100 + STM_Gap
						Right_Wheel     = 100 - STM_Gap
						Left_direction  = 1
						Right_direction = 1

					else: 
						Left_Wheel      = 100 + STM_Gap
						Right_Wheel     = 100 - STM_Gap
						Left_direction  = 1
						Right_direction = 1		

					cv2.line(canvas2, (canvas_width//2 + int((STM_Gap / STM_Weight_Value)*2), canvas_height), \
					( canvas_width//2 + int((STM_Gap / STM_Weight_Value)*2), canvas_height // 2), (255, 255, 255), 2, cv2.LINE_AA) 

					if abs(STM_Gap) < 30:
						print(f"Zero Gap || STM_Gap : {STM_Gap}")
						Zero_gap += 1
						if Zero_gap > 3:
							Init_distance = False 
							print("INIT Distance END")						
					else:
						Zero_gap = 0 
														
			elif len(R_lines) > 0 and len(L_lines) == 0:
				right_fit_line  = get_fitline(ROI_IMG, R_lines)

				if len(R_x1) < 3:
					R_x1.append(right_fit_line[0])
					R_y1.append(right_fit_line[1])
					R_x2.append(right_fit_line[2])
					R_y2.append(right_fit_line[3])
					x1 = int(sum(R_x1) / len(R_x1))
					y1 = int(sum(R_y1) / len(R_y1)) 
					x2 = int(sum(R_x2) / len(R_x2))
					y2 = int(sum(R_y2) / len(R_y2)) 
					Right_Avg_points_temp = [x1, y1, x2, y2]

				else:
					R_x1.append(right_fit_line[0])
					R_y1.append(right_fit_line[1])
					R_x2.append(right_fit_line[2])
					R_y2.append(right_fit_line[3])

					x1 = int(sum(R_x1[-3:]) / 3)
					y1 = int(sum(R_y1[-3:]) / 3)
					x2 = int(sum(R_x2[-3:]) / 3)
					y2 = int(sum(R_y2[-3:]) / 3)
					Right_Avg_points_temp = [x1, y1, x2, y2]

				cv2.line(canvas, (x1, y1), (x2, y2), (255,255,255), 2)					

				# Distance Moving Average + remove outliar 
				Right_distance = cal_dist(x1, y1, x2, y2, width // 2, height)
				if len(Right_pos_temp) <= 3: 
					if len(Right_pos_temp) < 2:
						Right_pos_temp.append(Right_distance) 
					else:
						if (abs(Right_pos_temp[-1] - Right_distance) > 50) and Right_Pos_flag < 3:
							Right_Pos_flag += 1
						else:
							Right_Pos_flag = 0 
							Right_pos_temp.append(Right_distance)
					Right_Avg_Pos = np.mean(Right_pos_temp)						
				else:
					if(abs(Right_pos_temp[-1] - Right_distance) > 50) and Right_Pos_flag < 3:
						Right_Pos_flag += 1
					else:
						Right_Pos_flag = 0 
						Right_pos_temp.append(Right_distance)
					Right_Avg_Pos = np.mean(Right_pos_temp[-3:])

					STM_Right_Dist 	= Right_Avg_Pos
					STM_Gap = ((STM_Right_Dist - Base_right_distance) / (Base_left_distance + Base_right_distance)) * 100 * 2
					STM_Gap = (STM_Gap * STM_Weight_Value) + STM_Ratio						

					if abs(STM_Gap) > 50:
						if STM_Gap > 0:
							STM_Gap = 50
						else:
							STM_Gap = -50

					if STM_Gap < 0: # Road line is on the right side of middle line
						Left_Wheel      = 100 + STM_Gap
						Right_Wheel     = 100 - STM_Gap
						Left_direction  = 1
						Right_direction = 1

					else: # Road line is on the left side of middle line
						Left_Wheel      = 100 + STM_Gap
						Right_Wheel     = 100 - STM_Gap
						Left_direction  = 1
						Right_direction = 1

					cv2.line(canvas2, (canvas_width//2 + int((STM_Gap / STM_Weight_Value)*2), canvas_height), \
					( canvas_width//2 + int((STM_Gap / STM_Weight_Value)*2), canvas_height // 2), (255, 255, 255), 2, cv2.LINE_AA) 

					if abs(STM_Gap) < 30:
						print(f"Zero Gap || STM_Gap : {STM_Gap}")						
						Zero_gap += 1
						if Zero_gap > 3:
							Init_distance = False 
							print("INIT Distance END")						
					else:
						Zero_gap = 0 
		
		elif (lines is None) and (Init_distance == True):

			No_line_flag += 1
			if No_line_flag >= 3:	
				Left_Wheel      = 50
				Right_Wheel     = 50
				Left_direction  = 1
				Right_direction = 1				

			else:
				if (Left_Avg_points_temp != 0) and (Right_Avg_points_temp != 0) :
					x1, y1, x2, y2 = Left_Avg_points_temp				
					cv2.line(canvas, (x1, y1), (x2, y2), (255,255,255), 2)					
					x1, y1, x2, y2 = Right_Avg_points_temp
					cv2.line(canvas, (x1, y1), (x2, y2), (255,255,255), 2)					

					STM_Left_Dist  = Left_Avg_Pos   
					STM_Right_Dist = Right_Avg_Pos  

					if (STM_Right_Dist + STM_Left_Dist) != 0:  # Except zero division
						# if Gap + : Left, Gap - : Right ee					
						STM_Gap = ((STM_Right_Dist - STM_Left_Dist) / (STM_Right_Dist + STM_Left_Dist)) * 100 
						STM_Gap = (STM_Gap * STM_Weight_Value) + STM_Ratio

						if abs(STM_Gap) > 50:
							if STM_Gap > 0:
								STM_Gap = 50
							else:
								STM_Gap = -50								

						if STM_Gap < 0: # Road line is on the right side of middle line
							Left_Wheel      = 100 + STM_Gap
							Right_Wheel     = 100 - STM_Gap
							Left_direction  = 1
							Right_direction = 1

						else:           # Road line is on the left side of middle line
							Left_Wheel      = 100 + STM_Gap
							Right_Wheel     = 100 - STM_Gap
							Left_direction  = 1
							Right_direction = 1		

					cv2.line(canvas2, (canvas_width//2 + int((STM_Gap / STM_Weight_Value)*2), canvas_height), \
					( canvas_width//2 + int((STM_Gap / STM_Weight_Value)*2), canvas_height // 2), (255, 255, 255), 2, cv2.LINE_AA) 

					if abs(STM_Gap) < 30:
						print(f"Zero Gap || STM_Gap : {STM_Gap}")
						Zero_gap += 1
						if Zero_gap > 3:
							Init_distance = False 
							print("INIT Distance END")						
					else:
						Zero_gap = 0 			
		
		# ----------------------- Initialize distance End ------------------- #		

		# ----------------------- Start Driving ------------------- #						
		if (lines is not None) and (Init_distance == False):			
			No_line_flag = 0             
			#if i == 100:			
			#	Stop_bit = 1
			#	print("#######################################")
			#	print("Turn Flag on")
			#	print("#######################################")

			# Eliminate axis 1
			lines2 = np.squeeze(lines, 1)
			slope_degree = (np.arctan2(lines2[:,1] - lines2[:,3], lines2[:,0] - lines2[:,2]) * 180) / np.pi

			lines2 = lines2[np.abs(slope_degree) < 150]
			slope_degree = slope_degree[np.abs(slope_degree) < 150]			
			lines2 = lines2[np.abs(slope_degree) > 30]
			slope_degree = slope_degree[np.abs(slope_degree) > 30]
									
			L_lines = lines2[(slope_degree) > 0, :]			
			R_lines = lines2[(slope_degree) < 0, :]

			# Restore axis 1
			L_lines = L_lines[:,None]
			R_lines = R_lines[:,None]				

			# Get Main Line of Left Side
			if len(L_lines) > 0:
				Left_line_interpolation = 0 				
				No_left_line_flag       = 0 
				left_fit_line  = get_fitline(ROI_IMG, L_lines)
				
				if len(L_x1) < 3:
					L_x1.append(left_fit_line[0])
					L_y1.append(left_fit_line[1])
					L_x2.append(left_fit_line[2])
					L_y2.append(left_fit_line[3])
					x1 = int(sum(L_x1) / len(L_x1))
					y1 = int(sum(L_y1) / len(L_y1))
					x2 = int(sum(L_x2) / len(L_x2)) 
					y2 = int(sum(L_y2) / len(L_y2)) 
					Left_Avg_points_temp = [x1, y1, x2, y2]

				else:
					L_x1.append(left_fit_line[0])
					L_y1.append(left_fit_line[1])
					L_x2.append(left_fit_line[2])
					L_y2.append(left_fit_line[3])

					x1 = int(sum(L_x1[-3:]) / 3)
					y1 = int(sum(L_y1[-3:]) / 3)
					x2 = int(sum(L_x2[-3:]) / 3)
					y2 = int(sum(L_y2[-3:]) / 3)
					Left_Avg_points_temp = [x1, y1, x2, y2]

				# Get angle and distance
				Left_Angle     = get_angle(left_fit_line)				
				Left_distance  = cal_dist(x1, y1, x2, y2, width//2, height)

				# Distance Moving Average + remove outliar 
				if len(Left_pos_temp) <= 3: 
					if len(Left_pos_temp) < 2:
						Left_pos_temp.append(Left_distance) 
					else:
						if (abs(Left_pos_temp[-1] - Left_distance) > 50) and Left_Pos_flag < 3:
							Left_Pos_flag += 1
						else:
							Left_Pos_flag = 0 
							Left_pos_temp.append(Left_distance)
					Left_Avg_Pos = np.mean(Left_pos_temp)						
				else:
					if(abs(Left_pos_temp[-1] - Left_distance) > 50) and Left_Pos_flag < 3:
						Left_Pos_flag += 1
					else:
						Left_Pos_flag = 0 
						Left_pos_temp.append(Left_distance)
					Left_Avg_Pos = np.mean(Left_pos_temp[-3:])

				# Angle Moving Average + remove outliar 
				if len(Left_angle_temp) <= 3: 
					if len(Left_angle_temp) < 2:
						Left_angle_temp.append(Left_Angle) 
					else:
						if (abs(Left_angle_temp[-1] - Left_Angle) > 20) and Left_Angle_flag < 3:
							Left_Angle_flag += 1
						else:
							Left_Angle_flag = 0 
							Left_angle_temp.append(Left_Angle)
					Left_Avg_Ang = np.mean(Left_angle_temp)						
				else:
					if(abs(Left_angle_temp[-1] - Left_Angle) > 20) and Left_Angle_flag < 3:
						Left_Angle_flag += 1
					else:
						Left_Angle_flag = 0 
						Left_angle_temp.append(Left_Angle)
					Left_Avg_Ang = np.mean(Left_angle_temp[-3:])

				cv2.line(canvas, (x1, y1), (x2, y2), (255,255,255), 2)								
				cv2.putText(canvas, "Left Angle        :" + str(Left_Angle),    (10, 20), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)	        
				cv2.putText(canvas, "Left Avg Angle    :" + str(Left_Avg_Ang),  (10, 40), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)	        				
				cv2.putText(canvas, "Left Distance     :" + str(Left_distance), (10, 60), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)					
				cv2.putText(canvas, "Left Avg Distance :" + str(Left_Avg_Pos),  (10, 80), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)	

			else: # Interpolation
				Left_line_interpolation += 1
				if Left_line_interpolation >= 3:
					Left_Avg_points_temp = 0
					Left_Angle           = Left_Base_angle     # Go straing 
					Left_Wheel           = Base_weight    # Go straing			
					No_left_line_flag    = 1
							
				elif (Left_line_interpolation < 3) and (Left_Avg_points_temp != 0):
					No_left_line_flag    = 0
					x1, y1, x2, y2 = Left_Avg_points_temp
					Left_distance = cal_dist(x1, y1, x2, y2, width//2, height)
					cv2.line(canvas, (x1, y1), (x2, y2), (255,255,255), 2)	
											
					cv2.putText(canvas, "Left Angle        :" + str(Left_Angle),    (10, 20), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)	        
					cv2.putText(canvas, "Left Avg Angle    :" + str(Left_Avg_Ang),  (10, 40), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)	        				
					cv2.putText(canvas, "Left Distance     :" + str(Left_distance), (10, 60), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)					
					cv2.putText(canvas, "Left Avg Distance :" + str(Left_Avg_Pos),  (10, 80), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)	

			# Get Main Line of Right Side
			if len(R_lines) > 0:
				Right_line_interpolation = 0 
				No_right_line_flag       = 0
				right_fit_line  = get_fitline(ROI_IMG, R_lines)

				if len(R_x1) < 3:
					R_x1.append(right_fit_line[0])
					R_y1.append(right_fit_line[1])
					R_x2.append(right_fit_line[2])
					R_y2.append(right_fit_line[3])
					x1 = int(sum(R_x1) / len(R_x1))
					y1 = int(sum(R_y1) / len(R_y1)) 
					x2 = int(sum(R_x2) / len(R_x2))
					y2 = int(sum(R_y2) / len(R_y2)) 
					Right_Avg_points_temp = [x1, y1, x2, y2]

				else:
					R_x1.append(right_fit_line[0])
					R_y1.append(right_fit_line[1])
					R_x2.append(right_fit_line[2])
					R_y2.append(right_fit_line[3])

					x1 = int(sum(R_x1[-3:]) / 3)
					y1 = int(sum(R_y1[-3:]) / 3)
					x2 = int(sum(R_x2[-3:]) / 3)
					y2 = int(sum(R_y2[-3:]) / 3)
					Right_Avg_points_temp = [x1, y1, x2, y2]

				# Get Angle and Distance
				Right_Angle     = get_angle(right_fit_line) 				
				Right_distance = cal_dist(x1, y1, x2, y2, width // 2, height)

				# Distance Moving Average + remove outliar 
				if len(Right_pos_temp) <= 3: 
					if len(Right_pos_temp) < 2:
						Right_pos_temp.append(Right_distance) 
					else:
						if (abs(Right_pos_temp[-1] - Right_distance) > 50) and Right_Pos_flag < 3:
							Right_Pos_flag += 1
						else:
							Right_Pos_flag = 0 
							Right_pos_temp.append(Right_distance)
					Right_Avg_Pos = np.mean(Right_pos_temp)						
				else:
					if(abs(Right_pos_temp[-1] - Right_distance) > 50) and Right_Pos_flag < 3:
						Right_Pos_flag += 1
					else:
						Right_Pos_flag = 0 
						Right_pos_temp.append(Right_distance)
					Right_Avg_Pos = np.mean(Right_pos_temp[-3:])
	
				# Angle Moving Average + remove outliar 
				if len(Right_angle_temp) <= 3: 
					if len(Right_angle_temp) < 2:
						Right_angle_temp.append(Right_Angle) 
					else:
						if (abs(Right_angle_temp[-1] - Right_Angle) > 20) and Right_Angle_flag < 3:
							Right_Angle_flag += 1
						else:
							Right_Angle_flag = 0 
							Right_angle_temp.append(Right_Angle)
					Right_Avg_Ang = np.mean(Right_angle_temp)						
				else:
					if(abs(Right_angle_temp[-1] - Right_Angle) > 20) and Right_Angle_flag < 3:
						Right_Angle_flag += 1
					else:
						Right_Angle_flag = 0 
						Right_angle_temp.append(Right_Angle)
					Right_Avg_Ang = np.mean(Right_angle_temp[-3:])

				# Draw
				cv2.line(canvas, (x1, y1), (x2, y2), (255,255,255), 2)	
				cv2.putText(canvas, "Right Angle        :"    + str(Right_Angle),    (10, 100), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)	
				cv2.putText(canvas, "Right Avg Angle    :"    + str(Right_Angle),    (10, 120), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)	
				cv2.putText(canvas, "Right Distance     :"    + str(Right_distance), (10, 140), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)					
				cv2.putText(canvas, "Right Avg Distance :"    + str(Right_Avg_Pos),  (10, 160), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)	

			else: # Interpolation
				Right_line_interpolation += 1
				if Right_line_interpolation >= 3:
					Right_Avg_points_temp = 0 
					Right_Angle           = Right_Base_angle
					Right_Wheel           = Base_weight    
					No_rightt_line_flag   = 1

				elif (Right_line_interpolation < 3) and (Right_Avg_points_temp != 0):			
					No_right_line_flag  = 1
					x1, y1, x2, y2      = Right_Avg_points_temp					
					Right_distance = cal_dist(x1, y1, x2, y2, width // 2, height)
					cv2.line(canvas, (x1, y1), (x2, y2), (255,255,255), 2)	
					cv2.putText(canvas, "Right Angle        :"    + str(Right_Angle),    (10, 100), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)	
					cv2.putText(canvas, "Right Avg Angle    :"    + str(Right_Angle),    (10, 120), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)	
					cv2.putText(canvas, "Right Distance     :"    + str(Right_distance), (10, 140), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)					
					cv2.putText(canvas, "Right Avg Distance :"    + str(Right_Avg_Pos),  (10, 160), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)	

		# Interpolation
		elif (lines is None) and (Init_distance == False) : 
			print("No line count : ", No_line_flag)
			No_line_flag += 1
			
			if No_line_flag >= 3:
				Left_Angle, Right_Angle = Left_Base_angle, Right_Base_angle
				Left_Wheel, Right_Wheel = Base_weight, Base_weight
				No_left_line_flag       = 1
				No_right_line_flag      = 1

			else:  # Interpolation
				if Left_Avg_points_temp != 0:
					No_left_line_flag    = 0
					x1, y1, x2, y2 = Left_Avg_points_temp
					Left_angle = get_angle([x1, y1, x2, y2])
					Left_distance = cal_dist(x1, y1, x2, y2, width // 2, height)	

					cv2.line(canvas, (x1, y1), (x2, y2), (255,255,255), 2)	
					cv2.putText(canvas, "Left Angle        :" + str(Left_Angle),    (10, 20), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)	        
					cv2.putText(canvas, "Left Avg Angle    :" + str(Left_Avg_Ang),  (10, 40), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)	        				
					cv2.putText(canvas, "Left Distance     :" + str(Left_distance), (10, 60), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)					
					cv2.putText(canvas, "Left Avg Distance :" + str(Left_Avg_Pos),  (10, 80), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)	

				if Right_Avg_points_temp != 0:
					No_right_line_flag    = 0
					x1, y1, x2, y2 = Right_Avg_points_temp
					Right_Angle = get_angle([x1, y1, x2, y2])
					Right_distance = cal_dist(x1, y1, x2, y2, width // 2, height)				
														
					cv2.line(canvas, (x1, y1), (x2, y2), (255,255,255), 2)	
					cv2.putText(canvas, "Right Angle        :"    + str(Right_Angle),    (10, 100), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)	
					cv2.putText(canvas, "Right Avg Angle    :"    + str(Right_Angle),    (10, 120), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)	
					cv2.putText(canvas, "Right Distance     :"    + str(Right_distance), (10, 140), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)					
					cv2.putText(canvas, "Right Avg Distance :"    + str(Right_Avg_Pos),  (10, 160), cv2.FONT_HERSHEY_PLAIN, 1, (255,255,255), 1, cv2.LINE_AA)	
				

		# Middle Line		
		cv2.line(canvas2, (canvas_width//2, canvas_height), (canvas_width//2, canvas_height//2), (255,255,255), 6, cv2.LINE_AA)		

		if (Init_distance == False):	# After angle, distance init finished ...		

			if (No_left_line_flag == 0) and (No_right_line_flag == 0) and (Left_Avg_points_temp != 0) and (Right_Avg_points_temp != 0):							

				STM_Left_Dist  = Left_Avg_Pos
				STM_Right_Dist = Right_Avg_Pos

				# if Gap + : Left, Gap - : Right ee
				STM_Gap = ((STM_Right_Dist - STM_Left_Dist) / (STM_Right_Dist + STM_Left_Dist)) * 100 
				STM_Gap = (STM_Gap * STM_Weight_Value) + STM_Ratio

				if abs(STM_Gap) > 50:
					if STM_Gap > 0:
						STM_Gap = 50
					else:
						STM_Gap = -50

				if STM_Gap < 0: # Road line is on the right side of middle line
					Left_Wheel      = 100 + STM_Gap
					Right_Wheel     = 100 - STM_Gap
					Left_direction  = 1
					Right_direction = 1

				else:           # Road line is on the left side of middle line
					Left_Wheel      = 100 + STM_Gap
					Right_Wheel     = 100 - STM_Gap
					Left_direction  = 1
					Right_direction = 1
				
				cv2.line(canvas2, (canvas_width//2 + int((STM_Gap / STM_Weight_Value)*2), canvas_height), \
				(canvas_width//2 + int((STM_Gap / STM_Weight_Value)*2), canvas_height // 2), (255, 255, 255), 2, cv2.LINE_AA) 


			if (No_left_line_flag == 1) and (No_right_line_flag == 0)  and (Right_Avg_points_temp != 0):			
				
				STM_Right_Dist 	= Right_Avg_Pos
				STM_Gap = ((STM_Right_Dist - Base_right_distance) / (Base_left_distance + Base_right_distance)) * 100 * 2
				STM_Gap = (STM_Gap * STM_Weight_Value) + STM_Ratio						

				if abs(STM_Gap) > 50:
					if STM_Gap > 0:
						STM_Gap = 50
					else:
						STM_Gap = -50

				if STM_Gap < 0: # Road line is on the right side of middle line
					Left_Wheel      = 100 + STM_Gap
					Right_Wheel     = 100 - STM_Gap
					Left_direction  = 1
					Right_direction = 1

				else: # Road line is on the left side of middle line
					Left_Wheel      = 100 + STM_Gap
					Right_Wheel     = 100 - STM_Gap
					Left_direction  = 1
					Right_direction = 1

				cv2.line(canvas2, (canvas_width//2 + int((STM_Gap / STM_Weight_Value)*2), canvas_height), \
				( canvas_width//2 + int((STM_Gap / STM_Weight_Value)*2), canvas_height // 2), (255, 255, 255), 2, cv2.LINE_AA) 

			if (No_left_line_flag == 0) and (No_right_line_flag == 1) and (Left_Avg_points_temp != 0):			
				
				STM_Left_Dist 	= Left_Avg_Pos
				STM_Gap = ((Base_left_distance  - STM_Left_Dist) / (Base_right_distance + Base_left_distance)) * 100 * 2
				STM_Gap = (STM_Gap * STM_Weight_Value) + STM_Ratio
						
				if abs(STM_Gap) > 50:
					if STM_Gap > 0:
						STM_Gap = 50
					else:
						STM_Gap = -50

				if STM_Gap < 0: # Road line is on the right side of middle line
					Left_Wheel      = 100 + STM_Gap
					Right_Wheel     = 100 - STM_Gap
					Left_direction  = 1
					Right_direction = 1

				else: # Road line is on the left side of middle line
					Left_Wheel      = 100 + STM_Gap
					Right_Wheel     = 100 - STM_Gap
					Left_direction  = 1
					Right_direction = 1

				cv2.line(canvas2, (canvas_width//2 + int((STM_Gap / STM_Weight_Value)*2), canvas_height), \
				( canvas_width//2 + int((STM_Gap / STM_Weight_Value)*2), canvas_height // 2), (255, 255, 255), 4, cv2.LINE_AA) 

		Left_Wheel  = int(Left_Wheel)
		Right_Wheel = int(Right_Wheel)

		if Left_Wheel <= 0:
			Send_Left_Wheel = str("000")
		elif Left_Wheel < 10:
			Send_Left_Wheel = str("00") + str(Left_Wheel)
		elif Left_Wheel < 100:			
			Send_Left_Wheel = str("0") + str(Left_Wheel)
		else:
			Send_Left_Wheel = str(Left_Wheel)

		if Right_Wheel <= 0:
			Send_Right_Wheel = str("000")
		elif Right_Wheel < 10:
			Send_Right_Wheel = str("00") + str(Right_Wheel)
		elif Right_Wheel < 100:			
			Send_Right_Wheel = str("0") + str(Right_Wheel)
		else:
			Send_Right_Wheel = str(Right_Wheel)			

		# UART
		print(f"Left Wheel : {Send_Left_Wheel} || Right_Wheel : {Send_Right_Wheel}")
		logger.info(f"START,{Stop_bit},R,{Send_Right_Wheel},D,{Right_direction},L,{Send_Left_Wheel},D,{Left_direction},Z")

		#Show images									
		canvas  = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
		canvas2 = cv2.cvtColor(canvas2, cv2.COLOR_BGR2GRAY)

		cv2.imshow("Color", color_image)

		merge = np.hstack((ROI_IMG, canvas, canvas2))
		cv2.imshow("ROI / Canvas1 / Canvas2", merge)		

		cv2.waitKey(1)

finally:
    # Stop streaming
    pipeline.stop()
