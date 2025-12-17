import math
import os
import zipfile
import pydicom
import numpy as np
from PyQt5.QtWidgets import QApplication, QTabWidget, QFileDialog, QVBoxLayout, QWidget, QInputDialog
from PyQt5.uic import loadUi
from PyQt5.QtCore import Qt
import pyqtgraph as pg
import logging
from vtk.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QPainter, QPen, QImage, QPixmap, QPolygonF
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel, QFileDialog, QLineEdit
from PIL import Image, ImageDraw, ImageFont
from PyQt5.QtGui import QImage, QPainter
import shutil
import cv2


logging.basicConfig(level=logging.INFO)

class MainWindow(QTabWidget): 
    def __init__(self, ui_file):
        super().__init__()
        loadUi(ui_file, self)
        self.full_screen = False

        self.tab_widget = QTabWidget() 
        # self.setCentralWidget(self.tab_widget)
        self.showFullScreen()

        self.setWindowTitle("DICOM Viewer")
        # Debugging to find the correct tab index
    
        self.dicom_images = []
        self.current_image_index = 0
        self.volume = None

        # Create a ViewBox inside the image_layout
        self.view_box = pg.ViewBox()
        self.image_layout.addItem(self.view_box)

        self.view_box1 = pg.ViewBox()
        self.image_layout1.addItem(self.view_box1)

        self.view_box2 = pg.ViewBox()
        self.image_layout2.addItem(self.view_box2)
        
        self.view_box_axial = pg.ViewBox()
        self.view_box_coronal = pg.ViewBox()
        self.view_box_sagittal= pg.ViewBox()
        self.axial_plane.addItem(self.view_box_axial)
        self.coronal_plane.addItem(self.view_box_coronal)
        self.sagittal_plane.addItem(self.view_box_sagittal)

        self.upload_btn.clicked.connect(self.load_dicom_zip)
        self.contrast_slider.setRange(0, 100)  # Set the range from 0 to 100
        self.contrast_slider.setValue(50)  # Default contrast value at 50
        self.contrast_slider.sliderReleased.connect(self.update_contrast) 

        self.upload_img2_btn.clicked.connect(self.load_dicom_zip)

        self.save_button.clicked.connect(self.save_annotations)
        self.clear_button.clicked.connect(self.clear_annotations)

        # Add placeholders for annotation and measurement tools
        self.annotations = []
        self.notes = {}
        self.text_items = []
        self.polygon_points = []
        self.dicom_images2 = []

        # Set up variables for annotation and measurement
        self.start_point = None
        self.end_point = None
        self.line_item = None
        self.annotation_active = False
        self.current_tool = 'line'  # Default tool
        self.counter = 0

        self.temp_dir = 'temp_dicom_images'
        self.temp_dir2 = 'temp_dicom_images2'

        self.label_wl.hide()
        self.label_ww.hide()
        self.input_wl.hide()
        self.input_ww.hide()

        self.comboBox_windowing.currentIndexChanged.connect(self.handle_showing)

        # windowing/Leveling
        self.comboBox_windowing.currentIndexChanged.connect(self.Windowing_and_Leveling)
        self.apply_windowing_btn.clicked.connect(self.Windowing_and_Leveling)

        # smoothing 
        self.apply_smoothing_btn.clicked.connect(self.smoothing)
        # noise reduction
        self.apply_noise_btn.clicked.connect(self.noise_reduction)

        # sharpening
        self.comboBox_sharpening.currentIndexChanged.connect(self.create_sharpening_for_planes)


        # Set up mouse events for drawing and measurement
        self.image_layout.setMouseTracking(True)  # Enable mouse tracking
        self.image_layout.mousePressEvent = self.mouse_press_event
        self.image_layout.mouseMoveEvent = self.mouse_move_event
        self.image_layout.mouseReleaseEvent = self.mouse_release_event

        #add button to toggle annotation
        self.annotationButton.stateChanged.connect(self.toggle_annotation)

        # Add a QPushButton to save the annotated image
        self.saveimg.clicked.connect(self.save_annotated_image)

        #change annotation tool
        self.comboBox.currentIndexChanged.connect(self.update_tool)
        
        
        
        #---------------------------------Volume Rendering---------------------------------
        self.load.clicked.connect(self.load_file)
        
        # Create a QVTKRenderWindowInteractor widget
        self.vtkWidget = QVTKRenderWindowInteractor(self.VR_widget)
        vbox = QVBoxLayout()
        vbox.addWidget(self.vtkWidget)
        self.VR_widget.setLayout(vbox)
        
        # Create a VTK Renderer
        self.renderer = vtk.vtkRenderer()
        self.vtkWidget.GetRenderWindow().AddRenderer(self.renderer)
        
        # Check if the combobox text is changed
        self.VR_comboBox.currentIndexChanged.connect(self.combobox_changed)
        
        # Adjust iso slider
        self.iso_slider.setMinimum(-243)
        self.iso_slider.setMaximum(1500)  
        self.iso_slider.setValue(200)
        
        # Check if the iso slider value is changed
        self.iso_slider.valueChanged.connect(self.update_isoValue)
        
        # Adjust lcd number
        self.lcdNumber.setDigitCount(200) 
        self.lcdNumber.display(self.iso_slider.value())

    def handle_showing(self):
        print(self.comboBox_windowing.currentText())
        if self.comboBox_windowing.currentText() == 'Custom Window':
            self.label_wl.show()
            self.label_ww.show()
            self.input_wl.show()
            self.input_ww.show()
        else:
            self.label_wl.hide()
            self.label_ww.hide()
            self.input_wl.hide()
            self.input_ww.hide()

    def load_dicom_zip(self):
        # Ask user to select a .zip file containing DICOM images
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.ExistingFiles)
        file_dialog.setNameFilter("Zip Files (*.zip)")
        if file_dialog.exec_():
            zip_file = file_dialog.selectedFiles()[0]
            if zip_file.endswith('.zip'):
                if self.counter ==0:
                    self.extract_dicom_images(zip_file)
                else:
                    self.extract_dicom_images2(zip_file)


    

    def extract_dicom_images(self, zip_file):
        self.counter += 1
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

        # Extract the DICOM files from the zip archive
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            # Extract all files to a temporary directory
            self.temp_dir = 'temp_dicom_images'
            os.makedirs(self.temp_dir, exist_ok=True)
            zip_ref.extractall(self.temp_dir)

        # Recursively find all DICOM files in the extracted directory
        dicom_files = []
        for root, _, files in os.walk(self.temp_dir):
            for file in files:
                if file.endswith('.dcm'):
                    dicom_files.append(os.path.join(root, file))

        # Ensure files are sorted
        dicom_files.sort()

        # Load DICOM images
        self.dicom_images = []
        self.dicom_metadata = []
        self.dicom_file_paths = []
        for dicom_file in dicom_files:
            dicom_data = pydicom.dcmread(dicom_file)
            image = dicom_data.pixel_array  # Get pixel data as numpy array
            self.dicom_images.append(image)
            self.dicom_metadata.append(dicom_data)
            self.dicom_file_paths.append(dicom_file)

        # Show the first image
        if self.dicom_images:
            self.current_image_index = 0  # Reset index for new data
            self.show_image(self.current_image_index)
            self.MPR()


    def extract_dicom_images2(self, zip_file):
        if os.path.exists(self.temp_dir2):
            shutil.rmtree(self.temp_dir2)

        # Extract the DICOM files from the zip archive
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            # Extract all files to a temporary directory
            self.temp_dir2 = 'temp_dicom_images2'
            os.makedirs(self.temp_dir2, exist_ok=True)
            zip_ref.extractall(self.temp_dir2)

        # Recursively find all DICOM files in the extracted directory
        dicom_files2 = []
        for root, _, files in os.walk(self.temp_dir2):
            for file in files:
                if file.endswith('.dcm'):
                    dicom_files2.append(os.path.join(root, file))

        # Ensure files are sorted, if necessary
        dicom_files2.sort()

        # Load DICOM images
        self.dicom_images2 = []
        self.dicom_metadata2 = []
        for dicom_file in dicom_files2:
            dicom_data = pydicom.dcmread(dicom_file)
            image = dicom_data.pixel_array  # Get pixel data as numpy array
            self.dicom_images2.append(image)
            self.dicom_metadata2.append(dicom_data)


    def show_image(self, index):
        # Show the DICOM image in the ViewBox
        if 0 <= index < len(self.dicom_images):
            img_data = self.dicom_images[index]
            # img_data = np.uint8(img_data)  # Ensure image data is in the correct format
            
            # Clear any previous image in the ViewBox
            self.view_box.clear()
              # Verify image is at least 2D
            if img_data.ndim < 2:
                raise ValueError(f"Invalid slice shape: {img_data.shape}")
            img_data = np.rot90(img_data, -1)
            image_item = pg.ImageItem(img_data)
            self.view_box.addItem(image_item)

            # Optionally, lock the aspect ratio (so images do not distort)
            self.view_box.setAspectLocked(True)

            # Clear any previous image in the ViewBox
            self.view_box1.clear()
            if img_data.ndim < 2:
                raise ValueError(f"Invalid slice shape: {img_data.shape}")
            image_item = pg.ImageItem(img_data)
            self.view_box1.addItem(image_item)

            # Optionally, lock the aspect ratio (so images do not distort)
            self.view_box1.setAspectLocked(True)
        
    
    def stacking_slices(self):
        self.volume = np.stack(self.dicom_images,axis=0)
    

    def MPR(self):

        axial_img_data,  coronal_img_data, sagittal_img_data = self.get_planes()
    
        ## show sagittal
        self.view_box_sagittal.clear()
        sagittal_img_data = np.fliplr(np.rot90(sagittal_img_data,-1))
        sagittal_img_data = pg.ImageItem(sagittal_img_data)
        self.view_box_sagittal.addItem(sagittal_img_data)
        self.view_box_sagittal.setAspectLocked(True)
        
        ## show axial
        self.view_box_axial.clear()
        axial_img_data = np.rot90(axial_img_data, -1)
        axial_img_data = pg.ImageItem(axial_img_data)
        self.view_box_axial.addItem(axial_img_data)
        self.view_box_axial.setAspectLocked(True)

        ## show coronal
        self.view_box_coronal.clear()
        coronal_img_data = np.rot90(coronal_img_data)
        coronal_img_data = pg.ImageItem(coronal_img_data)
        self.view_box_coronal.addItem(coronal_img_data)
        self.view_box_coronal.setAspectLocked(True)

    def laplacian_filter(self,slice):
            # Define a sharpening kernel
        kernel = np.array([[0, -1, 0],   ## laplacian filter
                        [-1, 5, -1],
                        [0, -1, 0]])

        sharpened_image = cv2.filter2D(slice, -1, kernel)
        return sharpened_image
    

    def high_boost_filter(self,slice):
        # Step 1: Apply a low-pass filter (Gaussian Blur)
        blurred_image = cv2.GaussianBlur(slice, (7, 7), 0)

        # Step 2: Calculate the high-frequency details
        high_frequency = cv2.subtract(slice, blurred_image)

        # Step 3: Amplify the high-frequency details
        lambda_factor = 5  # Scaling factor for sharpening
        amplified_high_frequency = cv2.multiply(high_frequency, lambda_factor)

        # Step 4: Add amplified details to the original image
        unsharp_masked_image = cv2.add(slice, amplified_high_frequency)

        return unsharp_masked_image

    
    def Unsharp_mask_filter(seld,slice):
        # Step 1: Apply a low-pass filter (Gaussian Blur)
        blurred_image = cv2.GaussianBlur(slice, (7, 7), 0)

        # Step 2: Calculate the high-frequency details
        high_frequency = cv2.subtract(slice, blurred_image)

        # Step 3: Amplify the high-frequency details
        lambda_factor = 1  # Scaling factor for sharpening
        amplified_high_frequency = cv2.multiply(high_frequency, lambda_factor)

        # Step 4: Add amplified details to the original image
        unsharp_masked_image = cv2.add(slice, amplified_high_frequency)

        return unsharp_masked_image

    def create_sharpening_for_planes(self):
        axial_img_data,  coronal_img_data, sagittal_img_data = self.get_planes()
        if self.comboBox_sharpening.currentText() == 'Laplacian':
            sharpened_axial_img_data = self.laplacian_filter(axial_img_data)
            sharpened_coronal_img_data = self.laplacian_filter(coronal_img_data)
            sharpened_sagittal_img_data = self.laplacian_filter(sagittal_img_data)

        elif self.comboBox_sharpening.currentText() == 'High Boost':  
            sharpened_axial_img_data = self.high_boost_filter(axial_img_data)
            sharpened_coronal_img_data = self.high_boost_filter(coronal_img_data)
            sharpened_sagittal_img_data = self.high_boost_filter(sagittal_img_data) 

        else:
            sharpened_axial_img_data = self.Unsharp_mask_filter(axial_img_data)
            sharpened_coronal_img_data = self.Unsharp_mask_filter(coronal_img_data)
            sharpened_sagittal_img_data = self.Unsharp_mask_filter(sagittal_img_data) 


        ## show sagittal
        self.view_box_sagittal.clear()
        sagittal_img_data = np.fliplr(np.rot90(sharpened_sagittal_img_data,-1))
        sagittal_img_data = pg.ImageItem(sagittal_img_data)
        self.view_box_sagittal.addItem(sagittal_img_data)
        self.view_box_sagittal.setAspectLocked(True)
        
        ## show axial
        self.view_box_axial.clear()
        axial_img_data = np.rot90(sharpened_axial_img_data, -1)
        axial_img_data = pg.ImageItem(axial_img_data)
        self.view_box_axial.addItem(axial_img_data)
        self.view_box_axial.setAspectLocked(True)

        ## show coronal
        self.view_box_coronal.clear()
        coronal_img_data = np.rot90(sharpened_coronal_img_data)
        coronal_img_data = pg.ImageItem(coronal_img_data)
        self.view_box_coronal.addItem(coronal_img_data)
        self.view_box_coronal.setAspectLocked(True)




    def noise_reduction(self):
        axial_img_data,  coronal_img_data, sagittal_img_data = self.get_planes()
        kernel_size = int(self.input_ksize_noise.text())
        # Median filter
        axial_denoised_image = cv2.medianBlur(axial_img_data, kernel_size)    
        sagittal_denoised_image = cv2.medianBlur(sagittal_img_data, kernel_size) 
        coronal_denoised_image = cv2.medianBlur(coronal_img_data, kernel_size) 
        
        ## show sagittal
        self.view_box_sagittal.clear()
        sagittal_img_data = np.fliplr(np.rot90(sagittal_denoised_image,-1))
        sagittal_img_data = pg.ImageItem(sagittal_img_data)
        self.view_box_sagittal.addItem(sagittal_img_data)
        self.view_box_sagittal.setAspectLocked(True)
        
        ## show axial
        self.view_box_axial.clear()
        axial_img_data = np.rot90(axial_denoised_image, -1)
        axial_img_data = pg.ImageItem(axial_img_data)
        self.view_box_axial.addItem(axial_img_data)
        self.view_box_axial.setAspectLocked(True)

        ## show coronal
        self.view_box_coronal.clear()
        coronal_img_data = np.rot90(coronal_denoised_image)
        coronal_img_data = pg.ImageItem(coronal_img_data)
        self.view_box_coronal.addItem(coronal_img_data)
        self.view_box_coronal.setAspectLocked(True)


       

    def smoothing(self):
        axial_img_data,  coronal_img_data, sagittal_img_data = self.get_planes()
        kernel_size = int(self.input_ksize_smoothing.text())
    
        # Gaussian blur
        axial_smoothed_image = cv2.GaussianBlur(axial_img_data, (kernel_size, kernel_size), 0)  
        coronal_smoothed_image = cv2.GaussianBlur(coronal_img_data, (kernel_size, kernel_size), 0)   
        sagittal_smoothed_image = cv2.GaussianBlur(sagittal_img_data, (kernel_size, kernel_size), 0)  
        ## show sagittal
        self.view_box_sagittal.clear()
        sagittal_img_data = np.fliplr(np.rot90(sagittal_smoothed_image,-1))
        sagittal_img_data = pg.ImageItem(sagittal_img_data)
        self.view_box_sagittal.addItem(sagittal_img_data)
        self.view_box_sagittal.setAspectLocked(True)
        
        ## show axial
        self.view_box_axial.clear()
        axial_img_data = np.rot90(axial_smoothed_image, -1)
        axial_img_data = pg.ImageItem(axial_img_data)
        self.view_box_axial.addItem(axial_img_data)
        self.view_box_axial.setAspectLocked(True)

        ## show coronal
        self.view_box_coronal.clear()
        coronal_img_data = np.rot90(coronal_smoothed_image)
        coronal_img_data = pg.ImageItem(coronal_img_data)
        self.view_box_coronal.addItem(coronal_img_data)
        self.view_box_coronal.setAspectLocked(True)
        


    def Windowing_and_Leveling(self):
        WL=0
        WW=0
        axial_img_data,  coronal_img_data, sagittal_img_data = self.get_planes()

        if self.comboBox_windowing.currentText() == 'Custom Window':
            WL = int(self.input_wl.text())
            WW = int(self.input_ww.text())

            print(WL, WW)
            axial_img_data = axial_img_data.astype(np.float32)
            coronal_img_data = coronal_img_data.astype(np.float32)
            sagittal_img_data = sagittal_img_data.astype(np.float32)

            # Apply windowing
            windowed_axial_img_data = np.clip((axial_img_data - (WL - 0.5)) / (WW - 1) + 0.5, 0, 1) * 255
            windowed_axial_img_data = windowed_axial_img_data.astype(np.uint8)

            windowed_coronal_img_data = np.clip((coronal_img_data - (WL - 0.5)) / (WW - 1) + 0.5, 0, 1) * 255
            windowed_coronal_img_data= windowed_coronal_img_data.astype(np.uint8)

            windowed_sagittal_img_data = np.clip((sagittal_img_data - (WL - 0.5)) / (WW - 1) + 0.5, 0, 1) * 255
            windowed_sagittal_img_data= windowed_sagittal_img_data.astype(np.uint8)

            ## show sagittal
            self.view_box_sagittal.clear()
            sagittal_img_data = np.fliplr(np.rot90(windowed_sagittal_img_data,-1))
            sagittal_img_data = pg.ImageItem(sagittal_img_data)
            self.view_box_sagittal.addItem(sagittal_img_data)
            self.view_box_sagittal.setAspectLocked(True)
            
            ## show axial
            self.view_box_axial.clear()
            axial_img_data = np.rot90(windowed_axial_img_data, -1)
            axial_img_data = pg.ImageItem(axial_img_data)
            self.view_box_axial.addItem(axial_img_data)
            self.view_box_axial.setAspectLocked(True)

            ## show coronal
            self.view_box_coronal.clear()
            coronal_img_data = np.rot90(windowed_coronal_img_data)
            coronal_img_data = pg.ImageItem(coronal_img_data)
            self.view_box_coronal.addItem(coronal_img_data)
            self.view_box_coronal.setAspectLocked(True)
        elif self.comboBox_windowing.currentText() == 'Default Window':
            self.MPR()
        else:
            WL = int(self.comboBox_windowing.currentText().split('/')[0][1:])
            WW = int(self.comboBox_windowing.currentText().split('/')[1][0:-1])
            print(WL, WW)
            axial_img_data = axial_img_data.astype(np.float32)
            coronal_img_data = coronal_img_data.astype(np.float32)
            sagittal_img_data = sagittal_img_data.astype(np.float32)

            # Apply windowing
            windowed_axial_img_data = np.clip((axial_img_data - (WL - 0.5)) / (WW - 1) + 0.5, 0, 1) * 255
            windowed_axial_img_data = windowed_axial_img_data.astype(np.uint8)

            windowed_coronal_img_data = np.clip((coronal_img_data - (WL - 0.5)) / (WW - 1) + 0.5, 0, 1) * 255
            windowed_coronal_img_data= windowed_coronal_img_data.astype(np.uint8)

            windowed_sagittal_img_data = np.clip((sagittal_img_data - (WL - 0.5)) / (WW - 1) + 0.5, 0, 1) * 255
            windowed_sagittal_img_data= windowed_sagittal_img_data.astype(np.uint8)

            ## show sagittal
            self.view_box_sagittal.clear()
            sagittal_img_data = np.fliplr(np.rot90(windowed_sagittal_img_data,-1))
            sagittal_img_data = pg.ImageItem(sagittal_img_data)
            self.view_box_sagittal.addItem(sagittal_img_data)
            self.view_box_sagittal.setAspectLocked(True)
            
            ## show axial
            self.view_box_axial.clear()
            axial_img_data = np.rot90(windowed_axial_img_data, -1)
            axial_img_data = pg.ImageItem(axial_img_data)
            self.view_box_axial.addItem(axial_img_data)
            self.view_box_axial.setAspectLocked(True)

            ## show coronal
            self.view_box_coronal.clear()
            coronal_img_data = np.rot90(windowed_coronal_img_data)
            coronal_img_data = pg.ImageItem(coronal_img_data)
            self.view_box_coronal.addItem(coronal_img_data)
            self.view_box_coronal.setAspectLocked(True)



    def get_planes(self):
        
        self.stacking_slices()
        if self.volume is None:
            raise ValueError("NOt image founded")

        axial_index = self.volume.shape[0] // 2  # Midpoint slice along Z-axis
        coronal_index = self.volume.shape[1] // 2  # Midpoint slice along Y-axis
        sagittal_index = self.volume.shape[2] // 2  # Midpoint slice along X-axis
    
        
    
        # Determine which slice to show
    
        axial_img_data = self.volume[axial_index, :, :]  # Axial view
        
        coronal_img_data = self.volume[:, coronal_index, :]  # Coronal view
        
        sagittal_img_data = self.volume[:, :, sagittal_index]  # Sagittal view


        return  axial_img_data,  coronal_img_data, sagittal_img_data

    def normalize_data(self):
        volume_min = np.min(self.volume)
        volume_max = np.max(self.volume)
        normalized_volume = (self.volume- volume_min) / (volume_max - volume_min)
        return normalized_volume


    def wheelEvent(self, event):
        # Handle mouse wheel scrolling for image navigation
        delta = event.angleDelta().y()
        if delta > 0:
            self.current_image_index = min(self.current_image_index + 1, len(self.dicom_images) - 1)
        elif delta < 0:
            self.current_image_index = max(self.current_image_index - 1, 0)
        
        self.show_image(self.current_image_index)
        if self.dicom_images2:
           slice = self.find_closest_ct_slice()
           self.show_slice(slice.pixel_array)

    def show_slice(self, slice):
        self.view_box2.clear()
            # Verify image is at least 2D
        if slice.ndim < 2:
            raise ValueError(f"Invalid slice shape: {slice.shape}")
        slice = np.rot90(slice, -1)
        image_item = pg.ImageItem(slice)
        self.view_box2.addItem(image_item)

        self.view_box2.setAspectLocked(True)


    def calculate_center(self,image_position, orientation, pixel_spacing, rows, cols):
        """
        Calculate the center of a slice in 3D space.
        """
        row_vector = np.array(orientation[:3])  # Row direction vector
        col_vector = np.array(orientation[3:])  # Column direction vector

        # Calculate pixel spacing in real-world coordinates
        row_spacing, col_spacing = pixel_spacing

        # Center position: Add half dimensions to the origin
        center = (
            np.array(image_position) +
            (row_vector * (rows / 2) * row_spacing) +
            (col_vector * (cols / 2) * col_spacing)
        )
        return center

    def find_closest_ct_slice(self):
        """
        Find the closest CT slice to the given MRI slice based on spatial position.
        """
        mri_position = self.calculate_center(
            self.dicom_metadata[self.current_image_index].ImagePositionPatient,
            self.dicom_metadata[self.current_image_index].ImageOrientationPatient,
            self.dicom_metadata[self.current_image_index].PixelSpacing,
            self.dicom_metadata[self.current_image_index].Rows,
            self.dicom_metadata[self.current_image_index].Columns
        )
        
        closest_ct = None
        min_distance = float('inf')
        
        for ct_slice in self.dicom_metadata2:
            ct_position = self.calculate_center(
                ct_slice.ImagePositionPatient,
                ct_slice.ImageOrientationPatient,
                ct_slice.PixelSpacing,
                ct_slice.Rows,
                ct_slice.Columns
            )
            # Compute Euclidean distance
            distance = np.linalg.norm(mri_position - ct_position)
            if distance < min_distance:
                min_distance = distance
                closest_ct = ct_slice
        
        return closest_ct

    def update_contrast(self):
        # Get the current contrast value from the slider
        contrast_value = self.contrast_slider.value()
        
        # Adjust contrast using a simple formula
        if self.dicom_images:
            img_data = self.dicom_images[self.current_image_index]
            
            # Normalize the image to 0-1 range and apply contrast factor
            contrast_factor = contrast_value / 50  # Adjust this scaling as needed
            adjusted_image = img_data * contrast_factor
            
            # Clip the values to ensure they stay within valid range (e.g., 0-255 for 8-bit images)
            adjusted_image = np.clip(adjusted_image, 0, 255).astype(np.uint8)
            
            # Show the adjusted image
            self.show_adjusted_image(adjusted_image)


    def show_adjusted_image(self, img_data):
        # Show the adjusted image in the ViewBox
        self.view_box.clear()

        # Ensure the image is at least 2D
        if img_data.ndim < 2:
            raise ValueError(f"Invalid slice shape: {img_data.shape}")
        
        img_data = np.rot90(img_data, -1)
        image_item = pg.ImageItem(img_data)
        self.view_box.addItem(image_item)

        # Optionally, lock the aspect ratio
        self.view_box.setAspectLocked(True)

    def keyPressEvent(self, event):
        if event.key() == 16777216:  # Escape key to toggle full-screen mode
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        else:
            super().keyPressEvent(event)


    def update_tool(self):
        self.current_tool = self.comboBox.currentText()
        print(f"Tool changed to: {self.current_tool}")  # Debugging line

    def mouse_press_event(self, event):
        if self.annotation_active and event.button():
            self.start_point = self.view_box.mapToView(event.pos())
            # self.start_point = event.pos()
            self.line_item = None  # Reset line item
            if self.current_tool == 'freehand':
                self.path = QPolygonF([self.start_point])

    def mouse_move_event(self, event):
        if self.annotation_active and self.start_point is not None:
            if self.current_tool == 'line':
                if self.line_item is not None:
                    self.view_box.removeItem(self.line_item)
                self.end_point = self.view_box.mapToView(event.pos())
                self.line_item = self.draw_line(self.start_point, self.end_point)

            elif self.current_tool == 'freehand':
                self.end_point = self.view_box.mapToView(event.pos())
                self.path.append(self.end_point)
                if self.line_item is not None:
                    self.view_box.removeItem(self.line_item)
                self.line_item = self.draw_path(self.path)

            elif self.current_tool == 'circle':
                if self.line_item is not None:
                    self.view_box.removeItem(self.line_item)
                self.end_point = self.view_box.mapToView(event.pos())
                self.line_item = self.draw_circle(self.start_point, self.end_point)

    def mouse_release_event(self, event):
        if self.annotation_active and event.button() == Qt.LeftButton and self.start_point is not None:
            length = None

            if self.current_tool == 'line' and self.end_point is not None:
                # Finalize the line
                self.annotations.append((self.start_point, self.end_point))
                length = self.calculate_distance(self.start_point, self.end_point)

            elif self.current_tool == 'freehand':
                self.annotations.append(self.path)

            elif self.current_tool == 'circle' and self.end_point is not None:
                # Add circle annotation
                self.annotations.append((self.start_point, self.end_point))
                length = self.calculate_distance(self.start_point, self.end_point)

            if length or self.current_tool in ('freehand', 'circle'):
                # Ask for note
                note, ok = QInputDialog.getText(self, 'Add Note', f'Enter annotation note:')
                if not ok:
                    # If user cancels, remove the last annotation
                    self.view_box.removeItem(self.line_item)
                else:
                    # Set default note if empty
                    if not note:
                        note = f"Distance: {length:.2f} units" if self.current_tool in ('line', 'circle') else "Note"

                    if self.current_tool == 'line' or self.current_tool == 'circle':
                        self.notes[(self.point_to_tuple(self.start_point), self.point_to_tuple(self.end_point))] = (
                        note, length)
                    else:
                        self.notes[(self.path.boundingRect().center(), self.path.boundingRect().center())] = (
                        note, None)

                    self.display_notes()

                    # Update the measurement labels with distance and note
                    note_text = f"Distance: {length:.2f} units, Note: {note}" if length else f"Note: {note}"
                    self.measurement_label.setText(note_text)
                    self.measurement_label_2.setText(note_text)

                    # Display note beside the annotation
                    if self.current_tool == 'line':
                        self.add_note_label(note, self.start_point, self.end_point)
                    elif self.current_tool == 'freehand':
                        self.add_note_label(note, self.path.boundingRect().center(), self.path.boundingRect().center())
                    elif self.current_tool == 'circle':
                        self.add_note_label(note, self.start_point, self.end_point)

            # Reset points
            self.start_point = None
            self.end_point = None
            self.line_item = None
            self.path = None

    def toggle_annotation(self):
        self.annotation_active = self.annotationButton.isChecked()


    def draw_line(self, start, end):
        line = pg.LineSegmentROI([[start.x(), start.y()], [end.x(), end.y()]], pen='r')
        self.view_box.addItem(line)
        return line


    def draw_path(self,path):
        # Convert QPolygonF to numpy array of x and y coordinates
        x = [point.x() for point in path]
        y = [point.y() for point in path]
        line = pg.PlotDataItem(x, y, pen=QPen(Qt.red))
        self.view_box.addItem(line)
        return line

    def draw_circle(self, start, end):
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        diameter = math.sqrt(dx**2 + dy**2)
        ellipse = pg.EllipseROI([start.x(), start.y()], [diameter, diameter], pen='r')
        self.view_box.addItem(ellipse)
        return ellipse

    def calculate_distance(self, start, end):
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        return math.sqrt(dx ** 2 + dy ** 2)

    def display_notes(self):
        # Display notes in the UI
        notes_text = "\n".join(
            f"Annotation from {key[0]} to {key[1]}: {note[0]}, Length: {note[1]:.2f} units" for key, note in
            self.notes.items())
        self.measurement_label_2.setText(notes_text)

    def save_annotations(self, dicom_file):
        # Save the annotations and notes to the DICOM file or a separate record
        annotation_file = f"{dicom_file}_annotations.txt"
        with open(annotation_file, "w") as file:
            for (start, end), (note, length) in self.notes.items():
                file.write(f"Annotation from {start} to {end}: {note}, Length: {length:.2f} units\n")

    def clear_annotations(self):  # Clear all annotations and notes
        self.annotations = []
        self.notes = {}
        # Remove only annotation items and labels from the view box
        for item in self.view_box.addedItems.copy():  # create a copy to avoid iteration issues
            if isinstance(item, (pg.LineSegmentROI, pg.PlotDataItem, pg.EllipseROI, pg.TextItem)):
                self.view_box.removeItem(item)
        # Remove all items from the view box
        self.measurement_label.setText("Distance: 0.00 units")
        self.measurement_label_2.setText("")
        # self.lineEdit.setPlaceholderText("Enter notes here...")

    def add_note_label(self, note, start,end):
        # Calculate the midpoint of the line
        mid_x = (start.x() + end.x()) / 2
        mid_y = (start.y() + end.y()) / 2
        note_label = pg.TextItem(text=note, color='w', anchor=(0, 0.1))
        note_label.setPos(mid_x, mid_y)
        self.view_box.addItem(note_label)
        self.text_items.append(note_label)



    def point_to_tuple(self, point):
        return (point.x(), point.y())



    def save_annotated_image(self):
        # Grab the content of the view_box
        pixmap = self.image_layout.grab()

        # Save the pixmap to a file
        pixmap.save("annotated_image.png")

#----------------------------------Volume Rendering----------------------------------
    def load_file(self):
            # Clear the renderer
            self.renderer.RemoveAllViewProps()

            filePath, _ = QFileDialog.getOpenFileName(self, "Open File",
                "",  # The initial directory. Leave as "" to start from the working directory.
                "Files (*.dcm *.stl *.glb)"
            )
            if filePath:  # Check if a file was selected
                if filePath.endswith('.dcm'):
                    # Get the directory containing the DICOM files
                    dicomDir = os.path.dirname(filePath)

                    # Load the DICOM series
                    self.reader = vtk.vtkDICOMImageReader()
                    self.reader.SetDirectoryName(dicomDir)
                    self.reader.Update()

                    # Check if the data is 2D
                    extent = self.reader.GetOutput().GetExtent()
                    if extent[1] == extent[0] or extent[3] == extent[2] or extent[5] == extent[4]:
                        print("Error: The loaded DICOM data appears to be 2D. Try loading a series of DICOM files to form a 3D volume.")
                        return

                    # Create an image actor
                    imageActor = vtk.vtkImageActor()
                    imageActor.GetMapper().SetInputConnection(self.reader.GetOutputPort())

                    # Add the image actor to the renderer
                    self.renderer.AddActor(imageActor)

                    # Render the window
                    self.vtkWidget.GetRenderWindow().Render()

                
    def combobox_changed(self):
        # Clear the renderer
        self.renderer.RemoveAllViewProps()
        
        if self.VR_comboBox.currentText().strip() == "Surface Rendering":
            self.apply_surface_rendering()
        else:
            self.apply_ray_casting_rendering()
        print(repr(self.comboBox.currentText().strip()))
        print(repr("Surface Rendering"))
        
        # Render the window
        self.vtkWidget.GetRenderWindow().Render()
        
    def update_isoValue(self, value):
        # Update ISO value in the LCDNumber
        self.lcdNumber.display(value)
        print(self.iso_slider.value())

        # Check if the current combobox selection is 'Surface Rendering'
        if self.VR_comboBox.currentText() == "Surface Rendering ":
            # Apply surface rendering with the updated ISO value
            self.apply_surface_rendering()
        else:
            print("The current selection is not 'Surface Rendering'.")

    def apply_surface_rendering(self):
        # Clear the renderer
        self.renderer.RemoveAllViewProps()

        # Check if DICOM data is already loaded
        if not hasattr(self, 'reader'):
            print("Error: No DICOM data loaded. Load a DICOM file first.")
            return

        # Get ISO value from the slider
        isoValue = self.iso_slider.value()

        # Check if the loaded data is 2D
        extent = self.reader.GetOutput().GetExtent()
        if extent[1] == extent[0] or extent[3] == extent[2] or extent[5] == extent[4]:
            print("Error: The loaded DICOM data appears to be 2D. Try loading a series of DICOM files to form a 3D volume.")
            return

        # Create a marching cubes filter to extract the surface
        marchingCubes = vtk.vtkMarchingCubes()
        marchingCubes.SetInputConnection(self.reader.GetOutputPort())
        marchingCubes.SetValue(0, isoValue)  # Set ISO value

        # Create a mapper for the surface
        surfaceMapper = vtk.vtkPolyDataMapper()
        surfaceMapper.SetInputConnection(marchingCubes.GetOutputPort())

        # Disable scalar visibility to avoid color mapping
        surfaceMapper.ScalarVisibilityOff()

        # Create an actor for the surface
        surfaceActor = vtk.vtkActor()
        surfaceActor.SetMapper(surfaceMapper)

        # Set a neutral color (e.g., light gray)
        # surfaceActor.GetProperty().SetColor(0.8, 0.8, 0.8)  # RGB values for light gray
        # surfaceActor.GetProperty().SetColor(0.8, 0.5, 0.4)  # Medium skin tone
        # surfaceActor.GetProperty().SetColor(0.9, 0.7, 0.6)  # Light skin tone
        # surfaceActor.GetProperty().SetColor(0.5, 0.3, 0.2)  # Dark skin tone
        surfaceActor.GetProperty().SetColor(0.85, 0.65, 0.55)  # natural skin tone

        # Add the surface actor to the renderer
        self.renderer.AddActor(surfaceActor)

        # Render the window
        self.vtkWidget.GetRenderWindow().Render()
        
    def apply_ray_casting_rendering(self):
        # Clear the renderer
        self.renderer.RemoveAllViewProps()

        # Check if DICOM data is already loaded
        if not hasattr(self, 'reader'):
            print("Error: No DICOM data loaded. Load a DICOM file first.")
            return

        # Check if the loaded data is 2D
        extent = self.reader.GetOutput().GetExtent()
        if extent[1] == extent[0] or extent[3] == extent[2] or extent[5] == extent[4]:
            print("Error: The loaded DICOM data appears to be 2D. Try loading a series of DICOM files to form a 3D volume.")
            return

        # Create a volume mapper for ray casting rendering
        volumeMapper = vtk.vtkSmartVolumeMapper()
        volumeMapper.SetBlendModeToComposite()

        # Create a volume property
        volumeProperty = vtk.vtkVolumeProperty()
        volumeProperty.ShadeOn()
        volumeProperty.SetInterpolationTypeToLinear()

        # Create a color transfer function
        colorTransferFunction = vtk.vtkColorTransferFunction()
        colorTransferFunction.AddRGBPoint(0, 0.0, 0.0, 1.0)  # Blue at scalar value 0
        colorTransferFunction.AddRGBPoint(200, 1.0, 1.0, 1.0)  # White at scalar value 200
        colorTransferFunction.AddRGBPoint(1000, 1.0, 0.0, 0.0)  # Red at scalar value 1000

        # Set the color transfer function to the volume property
        volumeProperty.SetColor(colorTransferFunction)

        # Set opacity to 0.5 (semi-transparent)
        opacityFunction = vtk.vtkPiecewiseFunction()
        opacityFunction.AddPoint(0, 0.0)
        opacityFunction.AddPoint(255, 0.5)  # Adjust the values as needed
        volumeProperty.SetScalarOpacity(opacityFunction)

        # Create a volume
        volume = vtk.vtkVolume()
        volume.SetMapper(volumeMapper)
        volume.SetProperty(volumeProperty)

        # Get the output of the reader
        image_data = self.reader.GetOutput()

        # Set the input data for the volume mapper
        volumeMapper.SetInputData(image_data)

        # Set the volume to the renderer
        self.renderer.AddVolume(volume)

        # Render the window
        self.vtkWidget.GetRenderWindow().Render()
    

    # ----------------------------------Annotations----------------------------------
    def update_tool(self):
        self.current_tool = self.comboBox.currentText()
        print(f"Tool changed to: {self.current_tool}")  

    def mouse_press_event(self, event):
        if self.annotation_active and event.button() == Qt.LeftButton:
            pos = self.view_box.mapToView(event.pos())

            if self.current_tool == 'polygon':
                if not self.polygon_points:
                    self.highlight_first_point(pos)
                self.polygon_points.append(pos)
                if len(self.polygon_points) > 1:
                    self.draw_line(self.polygon_points[-2], pos)
                if len(self.polygon_points) > 2 and self.is_close(pos, self.polygon_points[0]):
                    # Close the polygon
                    self.polygon_points.append(self.polygon_points[0])
                    self.draw_line(self.polygon_points[-2], self.polygon_points[-1])
                    self.calculate_and_display_area()
                    self.polygon_points = []
            else:
                self.start_point = pos
                self.line_item = None  # Reset line item

    def mouse_move_event(self, event):
        if self.annotation_active and self.start_point is not None:
            if self.current_tool == 'line':
                if self.line_item is not None:
                    self.view_box.removeItem(self.line_item)
                self.end_point = self.view_box.mapToView(event.pos())
                self.line_item = self.draw_line(self.start_point, self.end_point)


            elif self.current_tool == 'circle':
                if self.line_item is not None:
                    self.view_box.removeItem(self.line_item)
                self.end_point = self.view_box.mapToView(event.pos())
                self.line_item = self.draw_circle(self.start_point, self.end_point)

    def mouse_release_event(self, event):
        if self.annotation_active and event.button() == Qt.LeftButton and self.start_point is not None:
            length = None
            start_tuple = self.point_to_tuple(self.start_point)
            end_tuple = self.point_to_tuple(self.end_point)

            if self.current_tool == 'line' and self.end_point is not None:
                # Finalize the line
                self.annotations.append((self.start_point, self.end_point))
                length = self.calculate_distance(self.start_point, self.end_point)


            elif self.current_tool == 'circle' and self.end_point is not None:
                # Add circle annotation
                self.annotations.append((self.start_point, self.end_point))
                length = self.calculate_distance(self.start_point, self.end_point)

            if length or self.current_tool == 'circle':
                # Ask for note
                note, ok = QInputDialog.getText(self, 'Add Note', f'Enter annotation note:')
                if not ok:
                    # If user cancels, remove the last annotation
                    self.view_box.removeItem(self.line_item)
                else:
                    # Set default note if empty
                    if not note:
                        note = f"Distance: {length:.2f} cm"

                    self.notes[(start_tuple, end_tuple)] = (note, length)
                    # Update the measurement labels with distance and note
                    note_text = f"Distance: {length:.2f} cm, Note: {note}" if length else f"Note: {note}"
                    self.measurement_label.setText(note_text)

                    # self.measurementLabel_2.setText(note_text)

                    # Display note beside the annotation
                    if self.current_tool == 'line':
                        self.add_note_label(note, self.start_point, self.end_point)
                    elif self.current_tool == 'circle':
                        self.add_note_label(note, self.start_point, self.end_point)

            # Reset points
            self.start_point = None
            self.end_point = None
            self.line_item = None
            self.path = None

    def toggle_annotation(self):
        self.annotation_active = self.annotationButton.isChecked()

    def draw_line(self, start, end):
        line = pg.LineSegmentROI([[start.x(), start.y()], [end.x(), end.y()]], pen='r')
        self.view_box.addItem(line)
        return line

    def draw_circle(self, start, end):
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        diameter = math.sqrt(dx ** 2 + dy ** 2)
        ellipse = pg.EllipseROI([start.x(), start.y()], [diameter, diameter], pen='r')
        self.view_box.addItem(ellipse)
        return ellipse

    def calculate_distance(self, start, end):
        # Ensure there is at least one DICOM file path
        if not self.dicom_file_paths:
            print("No DICOM files available to retrieve pixel spacing.")
            return 0

        # Use the first DICOM file path to get pixel spacing
        pixel_spacing = self.get_pixel_spacing(self.dicom_file_paths[0])
        spacing_x = pixel_spacing[0] / 10.0  # Convert to cm
        spacing_y = pixel_spacing[1] / 10.0  # Convert to cm

        # Calculate the distance in pixels and then convert to cm
        dx = (end.x() - start.x()) * spacing_x
        dy = (end.y() - start.y()) * spacing_y
        return math.sqrt(dx ** 2 + dy ** 2)

    def display_notes(self):
        # Display notes in the UI
        notes_text = "\n".join(
            f"Annotation from {key[0]} to {key[1]}: {note[0]}, Length: {note[1]:.2f} cm" for key, note in
            self.notes.items())
        self.measurement_label_2.setText(notes_text)

    def save_annotations(self, dicom_file):
        # Save the annotations and notes to the DICOM file or a separate record
        annotation_file = f"{dicom_file}_annotations.txt"
        with open(annotation_file, "w") as file:
            for (start, end), (note, length) in self.notes.items():
                file.write(f"Annotation from {start} to {end}: {note}, Length: {length:.2f} units\n")

    def add_note_label(self, note, start, end):
        # Calculate the midpoint of the line
        mid_x = (start.x() + end.x()) / 2
        mid_y = (start.y() + end.y()) / 2
        note_label = pg.TextItem(text=note, color='w', anchor=(0, 0.1))
        note_label.setPos(mid_x, mid_y)
        self.view_box.addItem(note_label)
        self.text_items.append(note_label)

    def point_to_tuple(self, point):
        return (point.x(), point.y())

    def is_close(self, pos1, pos2, threshold=50):
        return (pos1 - pos2).manhattanLength() < threshold
        # distance = math.sqrt((pos2.x() - pos1.x()) ** 2 + (pos2.y() - pos1.y()) ** 2)
        # return distance < threshold

    def highlight_first_point(self, pos):
        point_marker = pg.ScatterPlotItem([pos.x()], [pos.y()], size=10, pen=pg.mkPen(None),
                                          brush=pg.mkBrush(255, 0, 0, 255))
        self.view_box.addItem(point_marker)
        self.text_items.append(point_marker)

    def calculate_and_display_area(self):
        if len(self.polygon_points) < 3:
            return  # Not a valid polygon

        # Ensure there is at least one DICOM file path
        if not self.dicom_file_paths:
            print("No DICOM files available to retrieve pixel spacing.")
            return

        # Use the first DICOM file path to get pixel spacing
        pixel_spacing = self.get_pixel_spacing(self.dicom_file_paths[0])
        spacing_x = pixel_spacing[0] / 10.0  # Convert to cm
        spacing_y = pixel_spacing[1] / 10.0  # Convert to cm

        # Shoelace formula to calculate area in cm²
        n = len(self.polygon_points)
        area = 0
        for i in range(n - 1):
            x1, y1 = self.polygon_points[i].x() * spacing_x, self.polygon_points[i].y() * spacing_y
            x2, y2 = self.polygon_points[i + 1].x() * spacing_x, self.polygon_points[i + 1].y() * spacing_y
            area += (x1 * y2 - x2 * y1)
        area = abs(area) / 2.0

        # Display area as annotation note
        center_x = sum([point.x() * spacing_x for point in self.polygon_points]) / n
        center_y = sum([point.y() * spacing_y for point in self.polygon_points]) / n
        # Display area as annotation note
        center_x = sum([point.x() for point in self.polygon_points]) / n
        center_y = sum([point.y() for point in self.polygon_points]) / n
        note_label = pg.TextItem(text=f"Area: {area:.2f} cm²", color='w', anchor=(0.5, 0.5))
        note_label.setPos(center_x, center_y)
        self.view_box.addItem(note_label)
        self.text_items.append(note_label)
        self.measurement_label.setText(f"Area: {area:.2f} cm²")
        
        

    def get_pixel_spacing(self, dicom_file):
        ds = pydicom.dcmread(dicom_file)
        pixel_spacing = ds.PixelSpacing
        return pixel_spacing

    def clear_annotations(self):
        self.annotations = []
        self.notes = {}
        # Remove only annotation items and labels from the view box
        for item in self.view_box.addedItems.copy():  # create a copy to avoid iteration issues
            if isinstance(item, (pg.LineSegmentROI, pg.PlotDataItem, pg.EllipseROI, pg.TextItem, pg.ScatterPlotItem)):
                self.view_box.removeItem(item)
        # Remove all items from the view box
        self.measurement_label.setText("Distance: 0.00 cm")
        # self.measurement_label_2.setText("")
        # self.lineEdit.setPlaceholderText("Enter notes here...")

    def save_annotated_image(self):
        # Grab the content of the view_box
        pixmap = self.image_layout.grab()

        # Save the pixmap to a file
        pixmap.save("annotated_image.png")


if __name__ == '__main__':
    app = QApplication([])
    window = MainWindow("DICOMmain.ui")
    window.show()
    app.exec_()
