# By WASasquatch (Discord: WAS#0263)
#
# Copyright 2023 Jordan Thompson (WASasquatch)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to 
# deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, 
# and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER 
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN 
# THE SOFTWARE.


import torch, os, sys, subprocess, random, math, hashlib, json, time
import torch.nn as nn
import torchvision.transforms as transforms
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance, ImageOps, ImageDraw, ImageChops
from PIL.PngImagePlugin import PngInfo
from urllib.request import urlopen

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "comfy"))
sys.path.append('../ComfyUI')

import comfy.samplers
import comfy.sd
import comfy.utils

import comfy_extras.clip_vision

import model_management
import importlib

import nodes

# GLOBALS
MIDAS_INSTALLED = False

#! FUNCTIONS

# Freeze PIP modules
def packages():
    import sys, subprocess
    return [r.decode().split('==')[0] for r in subprocess.check_output([sys.executable, '-m', 'pip', 'freeze']).split()]
    
# Tensor to PIL
def tensor2pil(image):
    return Image.fromarray(np.clip(255. * image.cpu().numpy().squeeze(), 0, 255).astype(np.uint8))
            
# Convert PIL to Tensor
def pil2tensor(image):
    return torch.from_numpy(np.array(image).astype(np.float32) / 255.0).unsqueeze(0)
    
# PIL Hex
def pil2hex(image):
    return hashlib.sha256(np.array(tensor2pil(image)).astype(np.uint16).tobytes()).hexdigest().hex();
    
# Median Filter
def medianFilter(img, diameter, sigmaColor, sigmaSpace):
    import cv2 as cv
    diameter = int(diameter); sigmaColor = int(sigmaColor); sigmaSpace = int(sigmaSpace)
    img = img.convert('RGB')
    img = cv.cvtColor(np.array(img), cv.COLOR_RGB2BGR)
    img = cv.bilateralFilter(img, diameter, sigmaColor, sigmaSpace)
    img = cv.cvtColor(np.array(img), cv.COLOR_BGR2RGB)
    return Image.fromarray(img).convert('RGB')

# INSTALLATION CLEANUP
# Delete legacy nodes
legacy_was_nodes = ['fDOF_WAS.py','Image_Blank_WAS.py','Image_Blend_WAS.py','Image_Canny_Filter_WAS.py', 'Canny_Filter_WAS.py','Image_Combine_WAS.py','Image_Edge_Detection_WAS.py', 'Image_Film_Grain_WAS.py', 'Image_Filters_WAS.py', 'Image_Flip_WAS.py','Image_Nova_Filter_WAS.py','Image_Rotate_WAS.py','Image_Style_Filter_WAS.py','Latent_Noise_Injection_WAS.py','Latent_Upscale_WAS.py','MiDaS_Depth_Approx_WAS.py','NSP_CLIPTextEncoder.py','Samplers_WAS.py']
legacy_was_nodes_found = []
f_disp = False
for f in legacy_was_nodes:
    node_path_dir = os.getcwd()+'/ComfyUI/custom_nodes/'
    file = f'{node_path_dir}{f}'
    if os.path.exists(file):
        import zipfile
        if not f_disp:
            print('\033[34mWAS Node Suite:\033[0m Found legacy nodes. Archiving legacy nodes...')
            f_disp = True
        legacy_was_nodes_found.append(file)
if legacy_was_nodes_found:
    from os.path import basename
    archive = zipfile.ZipFile(f'{node_path_dir}WAS_Legacy_Nodes_Backup_{round(time.time())}.zip', "w")
    for f in legacy_was_nodes_found:
        archive.write(f, basename(f))
        try:
            os.remove(f)
        except OSError:
            pass
    archive.close()
if f_disp:
    print('\033[34mWAS Node Suite:\033[0m Legacy cleanup complete.')

#! IMAGE FILTER NODES

# IMAGE FILTER ADJUSTMENTS

class WAS_Image_Filters:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "brightness": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "contrast": ("FLOAT", {"default": 1.0, "min": -1.0, "max": 2.0, "step": 0.01}),
                "saturation": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 5.0, "step": 0.01}),
                "sharpness": ("FLOAT", {"default": 1.0, "min": -5.0, "max": 5.0, "step": 0.01}),
                "blur": ("INT", {"default": 0, "min": 0, "max": 16, "step": 1}),
                "gaussian_blur": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1024.0, "step": 0.1}),
                "edge_enhance": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "image_filters"

    CATEGORY = "WAS Suite/Image"

    def image_filters(self, image, brightness, contrast, saturation, sharpness, blur, gaussian_blur, edge_enhance):
    
        pil_image = None
        
        # Apply NP Adjustments
        if brightness > 0.0 or brightness < 0.0:
            # Apply brightness
            image = np.clip(image + brightness, 0.0, 1.0)
            
        if contrast > 1.0 or contrast < 1.0:
            # Apply contrast
            image = np.clip(image * contrast, 0.0, 1.0)
            
        # Apply PIL Adjustments
        if saturation > 1.0 or saturation < 1.0:
            #PIL Image
            pil_image = tensor2pil(image)
            # Apply saturation
            pil_image = ImageEnhance.Color(pil_image).enhance(saturation)
           
        if sharpness > 1.0 or sharpness < 1.0:
            # Assign or create PIL Image
            pil_image = pil_image if pil_image else tensor2pil(image)
            # Apply sharpness
            pil_image = ImageEnhance.Sharpness(pil_image).enhance(sharpness)
            
        if blur > 0:
            # Assign or create PIL Image
            pil_image = pil_image if pil_image else tensor2pil(image)
            # Apply blur
            for _ in range(blur):
                pil_image = pil_image.filter(ImageFilter.BLUR)
                
        if gaussian_blur > 0.0:
            # Assign or create PIL Image
            pil_image = pil_image if pil_image else tensor2pil(image)
            # Apply Gaussian blur
            pil_image = pil_image.filter(ImageFilter.GaussianBlur(radius = gaussian_blur))
            
        if edge_enhance > 0.0:
            # Assign or create PIL Image
            pil_image = pil_image if pil_image else tensor2pil(image)
            # Edge Enhancement
            edge_enhanced_img = pil_image.filter(ImageFilter.EDGE_ENHANCE_MORE)
            # Blend Mask
            blend_mask = Image.new(mode = "L", size = pil_image.size, color = (round(edge_enhance * 255)))
            # Composite Original and Enhanced Version
            pil_image = Image.composite(edge_enhanced_img, pil_image, blend_mask)
            # Clean-up
            del blend_mask, edge_enhanced_img
            
        # Output image
        out_image = ( pil2tensor(pil_image) if pil_image else image )

        return ( out_image, )
        
 

# IMAGE STYLE FILTER

class WAS_Image_Style_Filter:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "style": ([
                    "1977",
                    "aden",
                    "brannan",
                    "brooklyn",
                    "clarendon",
                    "earlybird",
                    "gingham",
                    "hudson",
                    "inkwell",
                    "kelvin",
                    "lark",
                    "lofi",
                    "maven",
                    "mayfair",
                    "moon",
                    "nashville",
                    "perpetua",
                    "reyes",
                    "rise",
                    "slumber",
                    "stinson",
                    "toaster",
                    "valencia",
                    "walden",
                    "willow",
                    "xpro2"
                ],),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "image_style_filter"

    CATEGORY = "WAS Suite/Image"

    def image_style_filter(self, image, style):
    
        # Install Pilgram
        if 'pilgram' not in packages():
            print("\033[34mWAS NS:\033[0m Installing Pilgram...")
            subprocess.check_call([sys.executable, '-m', 'pip', '-q', 'install', 'pilgram'])
            
        # Import Pilgram module
        import pilgram
        
        # Convert image to PIL
        image = tensor2pil(image)
        
        # Apply blending
        match style:
            case "1977":
                out_image = pilgram._1977(image)
            case "aden":
                out_image = pilgram.aden(image)
            case "brannan":
                out_image = pilgram.brannan(image)
            case "brooklyn":
                out_image = pilgram.brooklyn(image)
            case "clarendon":
                out_image = pilgram.clarendon(image)
            case "earlybird":
                out_image = pilgram.earlybird(image)
            case "gingham":
                out_image = pilgram.gingham(image)
            case "hudson":
                out_image = pilgram.hudson(image)
            case "inkwell":
                out_image = pilgram.inkwell(image)
            case "kelvin":
                out_image = pilgram.kelvin(image)
            case "lark":
                out_image = pilgram.lark(image)
            case "lofi":
                out_image = pilgram.lofi(image)
            case "maven":
                out_image = pilgram.maven(image)
            case "mayfair":
                out_image = pilgram.mayfair(image)
            case "moon":
                out_image = pilgram.moon(image)
            case "nashville":
                out_image = pilgram.nashville(image)
            case "perpetua":
                out_image = pilgram.perpetua(image)
            case "reyes":
                out_image = pilgram.reyes(image)
            case "rise":
                out_image = pilgram.rise(image)
            case "slumber":
                out_image = pilgram.slumber(image)
            case "stinson":
                out_image = pilgram.stinson(image)
            case "toaster":
                out_image = pilgram.toaster(image)
            case "valencia":
                out_image = pilgram.valencia(image)
            case "walden":
                out_image = pilgram.walden(image)
            case "willow":
                out_image = pilgram.willow(image)
            case "xpro2":
                out_image = pilgram.xpro2(image)
            case _:
                out_image = image
                
        out_image = out_image.convert("RGB")

        return ( torch.from_numpy(np.array(out_image).astype(np.float32) / 255.0).unsqueeze(0), )
        
        
# COMBINE NODE

class WAS_Image_Blending_Mode:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_a": ("IMAGE",),
                "image_b": ("IMAGE",),
                "mode": ([
                    "add",
                    "color",
                    "color_burn",
                    "color_dodge",
                    "darken",
                    "difference",
                    "exclusion",
                    "hard_light",
                    "hue",
                    "lighten",
                    "multiply",
                    "overlay",
                    "screen",
                    "soft_light"
                ],),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "image_blending_mode"

    CATEGORY = "WAS Suite/Image"

    def image_blending_mode(self, image_a, image_b, mode):
    
        # Install Pilgram
        if 'pilgram' not in packages():
            print("\033[34mWAS NS:\033[0m Installing Pilgram...")
            subprocess.check_call([sys.executable, '-m', 'pip', '-q', 'install', 'pilgram'])
            
        # Import Pilgram module
        import pilgram
        
        # Convert images to PIL
        img_a = tensor2pil(image_a)
        img_b = tensor2pil(image_b)
        
        # Apply blending
        match mode:
            case "color":
                out_image = pilgram.css.blending.color(img_a, img_b)
            case "color_burn":
                out_image = pilgram.css.blending.color_burn(img_a, img_b)
            case "color_dodge":
                out_image = pilgram.css.blending.color_dodge(img_a, img_b)
            case "darken":
                out_image = pilgram.css.blending.darken(img_a, img_b)
            case "difference":
                out_image = pilgram.css.blending.difference(img_a, img_b)
            case "exclusion":
                out_image = pilgram.css.blending.exclusion(img_a, img_b)
            case "hard_light":
                out_image = pilgram.css.blending.hard_light(img_a, img_b)
            case "hue":
                out_image = pilgram.css.blending.hue(img_a, img_b)
            case "lighten":
                out_image = pilgram.css.blending.lighten(img_a, img_b)
            case "multiply":
                out_image = pilgram.css.blending.multiply(img_a, img_b)
            case "add":
                out_image = pilgram.css.blending.normal(img_a, img_b)
            case "overlay":
                out_image = pilgram.css.blending.overlay(img_a, img_b)
            case "screen":
                out_image = pilgram.css.blending.screen(img_a, img_b)
            case "soft_light":
                out_image = pilgram.css.blending.soft_light(img_a, img_b)
            case _:
                out_image = img_a
                
        out_image = out_image.convert("RGB")

        return ( pil2tensor(out_image), )
      

      
# IMAGE BLEND NODE
        
class WAS_Image_Blend:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_a": ("IMAGE",),
                "image_b": ("IMAGE",),
                "blend_percentage": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "image_blend"

    CATEGORY = "WAS Suite/Image"

    def image_blend(self, image_a, image_b, blend_percentage):
    
        # Convert images to PIL
        img_a = tensor2pil(image_a)
        img_b = tensor2pil(image_b)

        # Blend image
        blend_mask = Image.new(mode = "L", size = img_a.size, color = (round(blend_percentage * 255)))
        blend_mask = ImageOps.invert(blend_mask)
        img_result = Image.composite(img_a, img_b, blend_mask)
        
        del img_a, img_b, blend_mask

        return ( pil2tensor(img_result), )        



# IMAGE TRANSPOSE

class WAS_Image_Transpose:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "image_overlay": ("IMAGE",),
                "width": ("INT", {"default": 512, "min": -48000, "max": 48000, "step": 1}),
                "height": ("INT", {"default": 512, "min": -48000, "max": 48000, "step": 1}),
                "X": ("INT", {"default": 0, "min": -48000, "max": 48000, "step": 1}),
                "Y": ("INT", {"default": 0, "min": -48000, "max": 48000, "step": 1}),
                "rotation": ("INT", {"default": 0, "min": -360, "max": 360, "step": 1}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "image_transpose"

    CATEGORY = "WAS Suite/Image"

    def image_transpose(self, image, mode="rescale", resampling="lanczos", rescale_factor=2, resize_width=1024, resize_height=1024):
        return ( pil2tensor(self.apply_transpose_image(tensor2pil(image), tensor2pil(image_overlay), (int(width), int(height)), (int(X), int(Y)), int(rotation))), )
        
    def apply_transpose_image(self, base_image, transpose_image, size, location, rotation):

        # Resize the base image to the desired size
        transpose_image = transpose_image.resize(size)

        # Rotate the transposed image
        transpose_image = transpose_image.rotate(rotation, expand=True)

        # Paste the transposed image onto the image
        result_image = base_image.paste(transpose_image, location, transpose_image)

        # Return the resulting image
        return result_image



# IMAGE RESCALE

class WAS_Image_Rescale:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mode": (["rescale","resize"],),
                "resampling": (["lanczos","nearest","bilinear","bicubic"],),
                "rescale_factor": ("FLOAT", {"default": 2, "min": 0.01, "max": 16.0, "step": 0.01}),
                "resize_width": ("INT", {"default": 1024, "min": 1, "max": 48000, "step": 1}),
                "resize_height": ("INT", {"default": 1536, "min": 1, "max": 48000, "step": 1}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "image_rescale"

    CATEGORY = "WAS Suite/Image"

    def image_rescale(self, image, mode="rescale", resampling="lanczos", rescale_factor=2, resize_width=1024, resize_height=1024):
        return ( pil2tensor(self.apply_resize_image(tensor2pil(image), mode, factor, width, height, resample)), )
        
    def apply_resize_image(self, image, mode='scale', factor=None, width=None, height=None, resample='bicubic'):

        # Get the current width and height of the image
        current_width, current_height = image.size
        
        # Calculate the new width and height based on the given mode and parameters
        if mode == 'rescale':
            new_width, new_height = int(current_width * factor), int(current_height * factor)
        else:
            new_width = width if width % 8 == 0 else width + (8 - width % 8)
            new_height = height if height % 8 == 0 else height + (8 - height % 8)
        
        # Define a dictionary of resampling filters
        resample_filters = {
            'nearest': 0,
            'bilinear': 2,
            'bicubic': 3,
            'lanczos': 1
        }
        
        # Resize the image using the given resampling filter
        resized_image = image.resize((new_width, new_height), resample=Image.Resampling(resample_filters(resample)))
        
        return resized_image


# LOAD IMAGE BATCH

class WAS_Load_Image_Batch:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "folder_path": ("STRING", {"default": './ComfyUI/input/', "multiline": False}),
                "index": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff})
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "load_batch_images"

    CATEGORY = "WAS Suite/IO"

    def load_batch_images(self, folder_path, index):

        if os.path.exists(folder_path):
                fl = self.BatchImageLoader(folder_path)
                image = fl.get_image_by_id(index) 
                self.image = image
            

        return ( pil2tensor(image), )
        
    class BatchImageLoader:
        def __init__(self, directory_path):
            self.image_paths = []
            self.load_images(directory_path)
            self.image_paths.sort()  # sort the image paths by name

        def load_images(self, directory_path):
            allowed_extensions = ('.jpeg', '.jpg', '.png', '.tiff', '.gif', '.bmp', '.webp')
            for file_name in os.listdir(directory_path):
                if file_name.lower().endswith(allowed_extensions):
                    image_path = os.path.join(directory_path, file_name)
                    self.image_paths.append(image_path)

        def get_image_by_id(self, image_id):
            if image_id < 0 or image_id >= len(self.image_paths):
                raise ValueError("Invalid image ID")
            return Image.open(self.image_paths[image_id])
            
    @classmethod
    def IS_CHANGED(s, **kwargs):
        return float("NaN")



# IMAGE PADDING

class WAS_Image_Padding:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "feathering": ("INT", {"default": 120, "min": 0, "max": 2048, "step": 1}),
                "feather_second_pass": (["true","false"],),
                "left_padding": ("INT", {"default": 512, "min": 8, "max": 48000, "step": 1}),
                "right_padding": ("INT", {"default": 512, "min": 8, "max": 48000, "step": 1}),
                "top_padding": ("INT", {"default": 512, "min": 8, "max": 48000, "step": 1}),
                "bottom_padding": ("INT", {"default": 512, "min": 8, "max": 48000, "step": 1}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "image_padding"

    CATEGORY = "WAS Suite/Image"

    def image_padding(self, image, feathering, left_padding, right_padding, top_padding, bottom_padding, feather_second_pass=True):
        return ( pil2tensor(self.apply_image_padding(tensor2pil(image), left_padding, right_padding, top_padding, bottom_padding, feathering, second_pass=True)), )
        
    def apply_image_padding(self, image, left_pad=100, right_pad=100, top_pad=100, bottom_pad=100, feather_radius=50, second_pass=True):
        # Create a mask for the feathered edge
        mask = Image.new('L', image.size, 255)
        draw = ImageDraw.Draw(mask)

        # Draw black rectangles at each edge of the image with the specified feather radius
        draw.rectangle((0, 0, feather_radius*2, image.height), fill=0)
        draw.rectangle((image.width-feather_radius*2, 0, image.width, image.height), fill=0)
        draw.rectangle((0, 0, image.width, feather_radius*2), fill=0)
        draw.rectangle((0, image.height-feather_radius*2, image.width, image.height), fill=0)

        # Blur the mask to create a smooth gradient between the black shapes and the white background
        mask = mask.filter(ImageFilter.GaussianBlur(radius=feather_radius))

        # Create a second mask for the additional feathering pass
        mask2 = Image.new('L', image.size, 255)
        draw2 = ImageDraw.Draw(mask2)

        # Draw black rectangles at each edge of the image with a smaller feather radius
        feather_radius2 = int(feather_radius / 4)
        draw2.rectangle((0, 0, feather_radius2*2, image.height), fill=0)
        draw2.rectangle((image.width-feather_radius2*2, 0, image.width, image.height), fill=0)
        draw2.rectangle((0, 0, image.width, feather_radius2*2), fill=0)
        draw2.rectangle((0, image.height-feather_radius2*2, image.width, image.height), fill=0)

        # Do second pass
        if second_pass:
            # Blur the second mask to create a smooth gradient between the black shapes and the white background
            mask2 = mask2.filter(ImageFilter.GaussianBlur(radius=feather_radius2))

        # Apply the second mask to the feathered image
        feathered_im = Image.new('RGBA', image.size, (0, 0, 0, 0))
        feathered_im.paste(image, (0, 0), mask2)

        # Calculate the new size of the image with padding added
        new_size = (feathered_im.width + left_pad + right_pad, feathered_im.height + top_pad + bottom_pad)

        # Create a new transparent image with the new size
        new_im = Image.new('RGBA', new_size, (0, 0, 0, 0))

        # Paste the feathered image onto the new image with the padding
        new_im.paste(feathered_im, (left_pad, top_pad))

        # Save the new image with alpha channel as a PNG file
        return new_im
            
        
        
# IMAGE THRESHOLD NODE
        
class WAS_Image_Threshold:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "threshold": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "image_threshold"

    CATEGORY = "WAS Suite/Image"

    def image_threshold(self, image, threshold=0.5):
        return ( pil2tensor(self.apply_threshold(tensor2pil(image), threshold)), )
        
    def apply_threshold(self, input_image, threshold=0.5):
        # Convert the input image to grayscale
        grayscale_image = input_image.convert('L')

        # Apply the threshold to the grayscale image
        threshold_value = int(threshold * 255)
        thresholded_image = grayscale_image.point(lambda x: 255 if x >= threshold_value else 0, mode='L')

        return thresholded_image
        
        
        
# IMAGE CHROMATIC ABERRATION NODE
        
class WAS_Image_Chromatic_Aberration:

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "red_offset": ("INT", {"default": 2, "min": -255, "max": 255, "step": 1}),
                "green_offset": ("INT", {"default": -1, "min": -255, "max": 255, "step": 1}),
                "blue_offset": ("INT", {"default": 1, "min": -255, "max": 255, "step": 1}),
                "intensity": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),         
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "image_chromatic_aberration"

    CATEGORY = "WAS Suite/Image"

    def image_chromatic_aberration(self, image, red_offset=4, green_offset=2, blue_offset=0, intensity=1):
        return ( pil2tensor(self.apply_chromatic_aberration(tensor2pil(image), red_offset, green_offset, blue_offset, intensity)), )
        

    def apply_chromatic_aberration(self, img, r_offset, g_offset, b_offset, intensity):
        # split the channels of the image
        r, g, b = img.split()

        # apply the offset to each channel
        r_offset_img = ImageChops.offset(r, r_offset, 0)
        g_offset_img = ImageChops.offset(g, 0, g_offset)
        b_offset_img = ImageChops.offset(b, 0, b_offset)

        # blend the original image with the offset channels
        blended_r = ImageChops.blend(r, r_offset_img, intensity)
        blended_g = ImageChops.blend(g, g_offset_img, intensity)
        blended_b = ImageChops.blend(b, b_offset_img, intensity)

        # merge the channels back into an RGB image
        result = Image.merge("RGB", (blended_r, blended_g, blended_b))

        return result

        
        
# IMAGE BLOOM FILTER
        
class WAS_Image_Bloom_Filter:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "radius": ("FLOAT", {"default": 10, "min": 0.0, "max": 1024, "step": 0.1}),
                "intensity": ("FLOAT", {"default": 1, "min": 0.0, "max": 1.0, "step": 0.1}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "image_bloom"

    CATEGORY = "WAS Suite/Image"

    def image_bloom(self, image, radius=0.5, intensity=1.0):
        return ( pil2tensor(self.apply_bloom_filter(tensor2pil(image), radius, intensity)), )
        
    def apply_bloom_filter(self, input_image, radius, bloom_factor):
        # Apply a blur filter to the input image
        blurred_image = input_image.filter(ImageFilter.GaussianBlur(radius=radius))

        # Subtract the blurred image from the input image to create a high-pass filter
        high_pass_filter = ImageChops.subtract(input_image, blurred_image)

        # Create a blurred version of the bloom filter
        bloom_filter = high_pass_filter.filter(ImageFilter.GaussianBlur(radius=radius*2))

        # Adjust brightness and levels of bloom filter
        bloom_filter = ImageEnhance.Brightness(bloom_filter).enhance(2.0)

        # Multiply the bloom image with the bloom factor
        bloom_filter = ImageChops.multiply(bloom_filter, Image.new('RGB', input_image.size, (int(255 * bloom_factor), int(255 * bloom_factor), int(255 * bloom_factor))))

        # Multiply the bloom filter with the original image using the bloom factor
        blended_image = ImageChops.screen(input_image, bloom_filter)

        return blended_image
            
        
        
# IMAGE REMOVE COLOR
        
class WAS_Image_Remove_Color:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "target_red": ("INT", {"default": 255, "min": 0, "max": 255, "step": 1}),
                "target_green": ("INT", {"default": 255, "min": 0, "max": 255, "step": 1}),
                "target_blue": ("INT", {"default": 255, "min": 0, "max": 255, "step": 1}),
                "replace_red": ("INT", {"default": 255, "min": 0, "max": 255, "step": 1}),
                "replace_green": ("INT", {"default": 255, "min": 0, "max": 255, "step": 1}),
                "replace_blue": ("INT", {"default": 255, "min": 0, "max": 255, "step": 1}),
                "clip_threshold": ("INT", {"default": 10, "min": 0, "max": 255, "step": 1}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "image_remove_color"

    CATEGORY = "WAS Suite/Image"

    def image_remove_color(self, image, clip_threshold=10, target_red=255, target_green=255, target_blue=255, replace_red=255, replace_green=255, replace_blue=255):
        return ( pil2tensor(self.apply_remove_color(tensor2pil(image), clip_threshold, (target_red, target_green, target_blue), (replace_red, replace_green, replace_blue))), )
        
    def apply_remove_color(self, image, threshold=10, color=(255, 255, 255), rep_color=(0, 0, 0)):
        # Create a color image with the same size as the input image
        color_image = Image.new('RGB', image.size, color)
        
        # Calculate the difference between the input image and the color image
        diff_image = ImageChops.difference(image, color_image)
        
        # Convert the difference image to grayscale
        gray_image = diff_image.convert('L')
        
        # Apply a threshold to the grayscale difference image
        mask_image = gray_image.point(lambda x: 255 if x > threshold else 0)
        
        # Invert the mask image
        mask_image = ImageOps.invert(mask_image)
        
        # Apply the mask to the original image
        result_image = Image.composite(Image.new('RGB', image.size, rep_color), image, mask_image)
        
        return result_image


# IMAGE BLEND MASK NODE
        
class WAS_Image_Blend_Mask:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_a": ("IMAGE",),
                "image_b": ("IMAGE",),
                "mask": ("IMAGE",),
                "blend_percentage": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "image_blend_mask"

    CATEGORY = "WAS Suite/Image"

    def image_blend_mask(self, image_a, image_b, mask, blend_percentage):
    
        # Convert images to PIL
        img_a = tensor2pil(image_a)
        img_b = tensor2pil(image_b)
        mask = ImageOps.invert(tensor2pil(mask).convert('L'))
        
        # Mask image
        masked_img = Image.composite(img_a, img_b, mask.resize(img_a.size))

        # Blend image
        blend_mask = Image.new(mode = "L", size = img_a.size, color = (round(blend_percentage * 255)))
        blend_mask = ImageOps.invert(blend_mask)
        img_result = Image.composite(img_a, masked_img, blend_mask)
        
        del img_a, img_b, blend_mask, mask

        return ( pil2tensor(img_result), )


# IMAGE BLANK NOE


class WAS_Image_Blank:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": { 
                        "width": ("INT", {"default": 512, "min": 8, "max": 4096, "step": 1}),
                        "height": ("INT", {"default": 512, "min": 8, "max": 4096, "step": 1}),
                        "red": ("INT", {"default": 255, "min": 0, "max": 255, "step": 1}),
                        "green": ("INT", {"default": 255, "min": 0, "max": 255, "step": 1}),
                        "blue": ("INT", {"default": 255, "min": 0, "max": 255, "step": 1}),
                    }
                }
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "blank_image"

    CATEGORY = "WAS Suite/Image"

    def blank_image(self, width, height, red, green, blue): 
    
        # Ensure multiples
        width = ( width // 8 ) * 8
        height = ( height // 8 ) * 8

        # Blend image
        blank = Image.new(mode = "RGB", size = (width, height), color = (red, green, blue))

        return ( pil2tensor(blank), )
        
        
# IMAGE HIGH PASS

class WAS_Image_High_Pass_Filter:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": { 
                        "image": ("IMAGE",),
                        "radius": ("INT", {"default": 10, "min": 1, "max": 500, "step": 1}),
                        "strength": ("FLOAT", {"default": 1.5, "min": 0.0, "max": 255.0, "step": 0.1})
                    }
                }
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "high_pass"

    CATEGORY = "WAS Suite/Image"

    def high_pass(self, image, radius=10, strength=1.5): 
        hpf = tensor2pil(image).convert('L')
        return ( pil2tensor(self.apply_hpf(hpf.convert('RGB'), radius, strength)), )
        
    def apply_hpf(self, img, radius=10, strength=1.5):

        # pil to numpy
        img_arr = np.array(img).astype('float')

        # Apply a Gaussian blur with the given radius
        blurred_arr = np.array(img.filter(ImageFilter.GaussianBlur(radius=radius))).astype('float')

        # Apply the High Pass Filter
        hpf_arr = img_arr - blurred_arr
        hpf_arr = np.clip(hpf_arr * strength, 0, 255).astype('uint8')

        # Convert the numpy array back to a PIL image and return it
        return Image.fromarray(hpf_arr, mode='RGB')
        

# IMAGE LEVELS NODE

class WAS_Image_Levels:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": { 
                        "image": ("IMAGE",),
                        "black_level": ("FLOAT", {"default": 0.0, "min": 0.0, "max":255.0, "step": 0.1}),
                        "mid_level": ("FLOAT", {"default": 127.5, "min": 0.0, "max": 255.0, "step": 0.1}),
                        "white_level": ("FLOAT", {"default": 255, "min": 0.0, "max": 255.0, "step": 0.1}),
                    }
                }
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "apply_image_levels"

    CATEGORY = "WAS Suite/Image"

    def apply_image_levels(self, image, black_level, mid_level, white_level): 
       
       # Convert image to PIL
       image = tensor2pil(image)
 
       #apply image levels
       #image = self.adjust_levels(image, black_level, mid_level, white_level)
       
       levels = self.AdjustLevels(black_level, mid_level, white_level)
       image = levels.adjust(image)
       
       # Return adjust image tensor
       return ( pil2tensor(image), )
       
    def adjust_levels(self, image, black=0.0, mid=1.0, white=255):
        """
        Adjust the black, mid, and white levels of an RGB image.
        """
        # Create a new empty image with the same size and mode as the original image
        result = Image.new(image.mode, image.size)

        # Check that the mid value is within the valid range
        if mid < 0 or mid > 1:
            raise ValueError("mid value must be between 0 and 1")

        # Create a lookup table to map the pixel values to new values
        lut = []
        for i in range(256):
            if i < black:
                lut.append(0)
            elif i > white:
                lut.append(255)
            else:
                lut.append(int(((i - black) / (white - black)) ** mid * 255.0))

        # Split the image into its red, green, and blue channels
        r, g, b = image.split()

        # Apply the lookup table to each channel
        r = r.point(lut)
        g = g.point(lut)
        b = b.point(lut)

        # Merge the channels back into an RGB image
        result = Image.merge("RGB", (r, g, b))

        return result
        
    class AdjustLevels:
        def __init__(self, min_level, mid_level, max_level):
            self.min_level = min_level
            self.mid_level = mid_level
            self.max_level = max_level

        def adjust(self, im):
            # load the image

            # convert the image to a numpy array
            im_arr = np.array(im)

            # apply the min level adjustment
            im_arr[im_arr < self.min_level] = self.min_level

            # apply the mid level adjustment
            im_arr = (im_arr - self.min_level) * (255 / (self.max_level - self.min_level))
            im_arr[im_arr < 0] = 0
            im_arr[im_arr > 255] = 255
            im_arr = im_arr.astype(np.uint8)

            # apply the max level adjustment
            im = Image.fromarray(im_arr)
            im = ImageOps.autocontrast(im, cutoff=self.max_level)

            return im


# FILM GRAIN NODE

class WAS_Film_Grain:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": { 
                        "image": ("IMAGE",),
                        "density": ("FLOAT", {"default": 1.0, "min": 0.01, "max": 1.0, "step": 0.01}),
                        "intensity": ("FLOAT", {"default": 1.0, "min": 0.01, "max": 1.0, "step": 0.01}),
                        "highlights": ("FLOAT", {"default": 1.0, "min": 0.01, "max": 255.0, "step": 0.01}),
                        "supersample_factor": ("INT", {"default": 4, "min": 1, "max": 8, "step": 1})
                    }
                }
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "film_grain"

    CATEGORY = "WAS Suite/Image"

    def film_grain(self, image, density, intensity, highlights, supersample_factor): 
        return ( pil2tensor(self.apply_film_grain(tensor2pil(image), density, intensity, highlights, supersample_factor)), )

    def apply_film_grain(self, img, density=0.1, intensity=1.0, highlights=1.0, supersample_factor = 4):
        """
        Apply grayscale noise with specified density, intensity, and highlights to a PIL image.
        """
        # Convert the image to grayscale
        img_gray = img.convert('L')
        
        # Super Resolution noise image
        original_size = img.size
        img_gray = img_gray.resize(((img.size[0] * supersample_factor), (img.size[1] * supersample_factor)), Image.Resampling(2))
        
        # Calculate the number of noise pixels to add
        num_pixels = int(density * img_gray.size[0] * img_gray.size[1])

        # Create a list of noise pixel positions
        noise_pixels = []
        for i in range(num_pixels):
            x = random.randint(0, img_gray.size[0]-1)
            y = random.randint(0, img_gray.size[1]-1)
            noise_pixels.append((x, y))

        # Apply the noise to the grayscale image
        for x, y in noise_pixels:
            value = random.randint(0, 255)
            img_gray.putpixel((x, y), value)

        # Convert the grayscale image back to RGB
        img_noise = img_gray.convert('RGB')
        
        # Blur noise image
        img_noise = img_noise.filter(ImageFilter.GaussianBlur(radius = 0.125))
        
        # Downsize noise image
        img_noise = img_noise.resize(original_size, Image.Resampling(1))
        
        # Sharpen super resolution result
        img_noise = img_noise.filter(ImageFilter.EDGE_ENHANCE_MORE)

        # Blend the noisy color image with the original color image
        img_final = Image.blend(img, img_noise, intensity)

        # Adjust the highlights
        enhancer = ImageEnhance.Brightness(img_final)
        img_highlights = enhancer.enhance(highlights)

        # Return the final image
        return img_highlights
  

# IMAGE FLIP NODE
  
class WAS_Image_Flip:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mode": (["horizontal", "vertical",],),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "image_flip"

    CATEGORY = "WAS Suite/Image"

    def image_flip(self, image, mode):
        
        # PIL Image
        image = tensor2pil(image)
        
        # Rotate Image
        if mode == 'horizontal':
            image = image.transpose(0)
        if mode == 'vertical':
            image = image.transpose(1)
        
        return ( pil2tensor(image), )


class WAS_Image_Rotate:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mode": (["transpose", "internal",],),
                "rotation": ("INT", {"default": 0, "min": 0, "max": 360, "step": 90}),
                "sampler": (["nearest", "bilinear", "bicubic"],),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "image_rotate"

    CATEGORY = "WAS Suite/Image"

    def image_rotate(self, image, mode, rotation, sampler):
        
        # PIL Image
        image = tensor2pil(image)
        
        # Check rotation
        if rotation > 360:
            rotation = int(360)
        if (rotation % 90 != 0):
            rotation = int((rotation//90)*90);
            
        # Set Sampler
        match sampler:
            case 'nearest':
                sampler = PIL.Image.NEAREST
            case 'bicubic':
                sampler = PIL.Image.BICUBIC
            case 'bilinear':
                sampler = PIL.Image.BILINEAR
        
        # Rotate Image
        if mode == 'internal':
            image = image.rotate(rotation, sampler)
        else:
            rot = int(rotation / 90)
            for _ in range(rot):
                image = image.transpose(2)
        
        return ( torch.from_numpy(np.array(image).astype(np.float32) / 255.0).unsqueeze(0), )


# IMAGE NOVA SINE FILTER

class WAS_Image_Nova_Filter:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "amplitude": ("FLOAT", {"default": 0.1, "min": 0.0, "max": 1.0, "step": 0.001}),
                "frequency": ("FLOAT", {"default": 3.14, "min": 0.0, "max": 100.0, "step": 0.001}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "nova_sine"

    CATEGORY = "WAS Suite/Image"

    def nova_sine(self, image, amplitude, frequency):
        
        # Convert image to numpy
        img = tensor2pil(image)
        
        # Convert the image to a numpy array
        img_array = np.array(img)

        # Define a sine wave function
        def sine(x, freq, amp):
            return amp * np.sin(2 * np.pi * freq * x)

        # Calculate the sampling frequency of the image
        resolution = img.info.get('dpi')  # PPI
        physical_size = img.size  # pixels

        if resolution is not None:
            # Convert PPI to pixels per millimeter (PPM)
            ppm = 25.4 / resolution
            physical_size = tuple(int(pix * ppm) for pix in physical_size)

        # Set the maximum frequency for the sine wave
        max_freq = img.width / 2
        
        # Ensure frequency isn't outside visual representable range
        if frequency > max_freq:
            frequency = max_freq

        # Apply levels to the image using the sine function
        for i in range(img_array.shape[0]):
            for j in range(img_array.shape[1]):
                for k in range(img_array.shape[2]):
                    img_array[i,j,k] = int(sine(img_array[i,j,k]/255, frequency, amplitude) * 255)

        return ( torch.from_numpy(img_array.astype(np.float32) / 255.0).unsqueeze(0), )


# IMAGE CANNY FILTER


class WAS_Canny_Filter:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "enable_threshold": (['false', 'true'],),
                "threshold_low": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "threshold_high": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "canny_filter"

    CATEGORY = "WAS Suite/Image"

    def canny_filter(self, image, threshold_low, threshold_high, enable_threshold):

        self.install_opencv()
        
        if enable_threshold == 'false':
            threshold_low = None
            threshold_high = None

        image_canny = Image.fromarray(self.Canny_detector(255. * image.cpu().numpy().squeeze(), threshold_low, threshold_high)).convert('RGB')

        return ( pil2tensor(image_canny), )
        
    # Defining the Canny Detector function
    # From: https://www.geeksforgeeks.org/implement-canny-edge-detector-in-python-using-opencv/
       
    # here weak_th and strong_th are thresholds for
    # double thresholding step
    def Canny_detector(self, img, weak_th = None, strong_th = None):
        
        import cv2
          
        # conversion of image to grayscale
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
           
        # Noise reduction step
        img = cv2.GaussianBlur(img, (5, 5), 1.4)
           
        # Calculating the gradients
        gx = cv2.Sobel(np.float32(img), cv2.CV_64F, 1, 0, 3)
        gy = cv2.Sobel(np.float32(img), cv2.CV_64F, 0, 1, 3)
          
        # Conversion of Cartesian coordinates to polar 
        mag, ang = cv2.cartToPolar(gx, gy, angleInDegrees = True)
           
        # setting the minimum and maximum thresholds 
        # for double thresholding
        mag_max = np.max(mag)
        if not weak_th:weak_th = mag_max * 0.1
        if not strong_th:strong_th = mag_max * 0.5
          
        # getting the dimensions of the input image  
        height, width = img.shape
           
        # Looping through every pixel of the grayscale 
        # image
        for i_x in range(width):
            for i_y in range(height):
                   
                grad_ang = ang[i_y, i_x]
                grad_ang = abs(grad_ang-180) if abs(grad_ang)>180 else abs(grad_ang)
                   
                # selecting the neighbours of the target pixel
                # according to the gradient direction
                # In the x axis direction
                if grad_ang<= 22.5:
                    neighb_1_x, neighb_1_y = i_x-1, i_y
                    neighb_2_x, neighb_2_y = i_x + 1, i_y
                  
                # top right (diagonal-1) direction
                elif grad_ang>22.5 and grad_ang<=(22.5 + 45):
                    neighb_1_x, neighb_1_y = i_x-1, i_y-1
                    neighb_2_x, neighb_2_y = i_x + 1, i_y + 1
                  
                # In y-axis direction
                elif grad_ang>(22.5 + 45) and grad_ang<=(22.5 + 90):
                    neighb_1_x, neighb_1_y = i_x, i_y-1
                    neighb_2_x, neighb_2_y = i_x, i_y + 1
                  
                # top left (diagonal-2) direction
                elif grad_ang>(22.5 + 90) and grad_ang<=(22.5 + 135):
                    neighb_1_x, neighb_1_y = i_x-1, i_y + 1
                    neighb_2_x, neighb_2_y = i_x + 1, i_y-1
                  
                # Now it restarts the cycle
                elif grad_ang>(22.5 + 135) and grad_ang<=(22.5 + 180):
                    neighb_1_x, neighb_1_y = i_x-1, i_y
                    neighb_2_x, neighb_2_y = i_x + 1, i_y
                   
                # Non-maximum suppression step
                if width>neighb_1_x>= 0 and height>neighb_1_y>= 0:
                    if mag[i_y, i_x]<mag[neighb_1_y, neighb_1_x]:
                        mag[i_y, i_x]= 0
                        continue
       
                if width>neighb_2_x>= 0 and height>neighb_2_y>= 0:
                    if mag[i_y, i_x]<mag[neighb_2_y, neighb_2_x]:
                        mag[i_y, i_x]= 0
       
        weak_ids = np.zeros_like(img)
        strong_ids = np.zeros_like(img)              
        ids = np.zeros_like(img)
           
        # double thresholding step
        for i_x in range(width):
            for i_y in range(height):
                  
                grad_mag = mag[i_y, i_x]
                  
                if grad_mag<weak_th:
                    mag[i_y, i_x]= 0
                elif strong_th>grad_mag>= weak_th:
                    ids[i_y, i_x]= 1
                else:
                    ids[i_y, i_x]= 2
           
        # finally returning the magnitude of
        # gradients of edges
        return mag
        
    def install_opencv(self):
        if 'opencv-python' not in packages():
            print("\033[34mWAS NS:\033[0m Installing CV2...")
            subprocess.check_call([sys.executable, '-m', 'pip', '-q', 'install', 'opencv-python'])


# IMAGE EDGE DETECTION

class WAS_Image_Edge:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mode": (["normal", "laplacian"],),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "image_edges"

    CATEGORY = "WAS Suite/Image"

    def image_edges(self, image, mode):
    
        # Convert image to PIL
        image = tensor2pil(image)

        # Detect edges
        match mode:
            case "normal":
                image = image.filter(ImageFilter.FIND_EDGES)
            case "laplacian":
                image = image.filter(ImageFilter.Kernel((3, 3), (-1, -1, -1, -1, 8,
                                              -1, -1, -1, -1), 1, 0))
            case _:
                image = image

        return ( torch.from_numpy(np.array(image).astype(np.float32) / 255.0).unsqueeze(0), )
     

# IMAGE FDOF NODE

class WAS_Image_fDOF:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "depth": ("IMAGE",),
                "mode": (["mock","gaussian","box"],),
                "radius": ("INT", {"default": 8, "min": 1, "max": 128, "step": 1}),
                "samples": ("INT", {"default": 1, "min": 1, "max": 3, "step": 1}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "fdof_composite"

    CATEGORY = "WAS Suite/Image"

    def fdof_composite(self, image, depth, radius, samples, mode):
    
        if 'opencv-python' not in packages():
            print("\033[34mWAS NS:\033[0m Installing CV2...")
            subprocess.check_call([sys.executable, '-m', 'pip', '-q', 'install', 'opencv-python'])
        
        import cv2 as cv

        #Convert tensor to a PIL Image
        i = 255. * image.cpu().numpy().squeeze()
        img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
        d = 255. * depth.cpu().numpy().squeeze()
        depth_img = Image.fromarray(np.clip(d, 0, 255).astype(np.uint8))

        #Apply Fake Depth of Field
        fdof_image = self.portraitBlur(img, depth_img, radius, samples, mode)

        return ( torch.from_numpy(np.array(fdof_image).astype(np.float32) / 255.0).unsqueeze(0), )

    def portraitBlur(self, img, mask, radius=5, samples=1, mode = 'mock'):
        mask = mask.resize(img.size).convert('L')
        if mode == 'mock':
            bimg = medianFilter(img, radius, (radius * 1500), 75)
        elif mode == 'gaussian':
            bimg = img.filter(ImageFilter.GaussianBlur(radius = radius))
        elif mode == 'box':
            bimg = img.filter(ImageFilter.BoxBlur(radius))
        bimg.convert(img.mode)
        rimg = None
        if samples > 1:
            for i in range(samples):
                if i == 0:
                    rimg = Image.composite(img, bimg, mask)
                else:
                    rimg = Image.composite(rimg, bimg, mask)
        else:
            rimg = Image.composite(img, bimg, mask).convert('RGB')
        
        return rimg
        
    # TODO: Implement lens_blur mode attempt
    def lens_blur(img, radius, amount, mask=None):
        """Applies a lens shape blur effect on an image.

        Args:
            img (numpy.ndarray): The input image as a numpy array.
            radius (float): The radius of the lens shape.
            amount (float): The amount of blur to be applied.
            mask (numpy.ndarray): An optional mask image specifying where to apply the blur.

        Returns:
            numpy.ndarray: The blurred image as a numpy array.
        """
        # Create a lens shape kernel.
        kernel = cv2.getGaussianKernel(ksize=int(radius * 10), sigma=0)
        kernel = np.dot(kernel, kernel.T)

        # Normalize the kernel.
        kernel /= np.max(kernel)

        # Create a circular mask for the kernel.
        mask_shape = (int(radius * 2), int(radius * 2))
        mask = np.ones(mask_shape) if mask is None else cv2.resize(mask, mask_shape, interpolation=cv2.INTER_LINEAR)
        mask = cv2.GaussianBlur(mask, (int(radius * 2) + 1, int(radius * 2) + 1), radius / 2)
        mask /= np.max(mask)

        # Adjust kernel and mask size to match input image.
        ksize_x = img.shape[1] // (kernel.shape[1] + 1)
        ksize_y = img.shape[0] // (kernel.shape[0] + 1)
        kernel = cv2.resize(kernel, (ksize_x, ksize_y), interpolation=cv2.INTER_LINEAR)
        kernel = cv2.copyMakeBorder(kernel, 0, img.shape[0] - kernel.shape[0], 0, img.shape[1] - kernel.shape[1], cv2.BORDER_CONSTANT, value=0)
        mask = cv2.resize(mask, (ksize_x, ksize_y), interpolation=cv2.INTER_LINEAR)
        mask = cv2.copyMakeBorder(mask, 0, img.shape[0] - mask.shape[0], 0, img.shape[1] - mask.shape[1], cv2.BORDER_CONSTANT, value=0)

        # Apply the lens shape blur effect on the image.
        blurred = cv2.filter2D(img, -1, kernel)
        blurred = cv2.filter2D(blurred, -1, mask * amount)

        if mask is not None:
            # Apply the mask to the original image.
            mask = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            img_masked = img * mask
            # Combine the masked image with the blurred image.
            blurred = img_masked * (1 - mask) + blurred

        return blurred
        
        
# IMAGE MEDIAN FILTER NODE
        
class WAS_Image_Median_Filter:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "diameter": ("INT", {"default": 2.0, "min": 0.1, "max": 255, "step": 1}),
                "sigma_color": ("FLOAT", {"default": 10.0, "min": -255.0, "max": 255.0, "step": 0.1}),
                "sigma_space": ("FLOAT", {"default": 10.0, "min": -255.0, "max": 255.0, "step": 0.1}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "apply_median_filter"

    CATEGORY = "WAS Suite/Image"

    def apply_median_filter(self, image, diameter, sigma_color, sigma_space):
        
        # Numpy Image
        image = tensor2pil(image)
        
        # Apply Median Filter effect
        image = medianFilter(image, diameter, sigma_color, sigma_space)
        
        return ( pil2tensor(image), )

# IMAGE SELECT COLOR
        
class WAS_Image_Select_Color:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "red": ("INT", {"default": 255.0, "min": 0.0, "max": 255.0, "step": 0.1}),
                "green": ("INT", {"default": 255.0, "min": 0.0, "max": 255.0, "step": 0.1}),
                "blue": ("INT", {"default": 255.0, "min": 0.0, "max": 255.0, "step": 0.1}),
                "variance": ("INT", {"default": 10, "min": 0, "max": 255, "step": 1}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "select_color"

    CATEGORY = "WAS Suite/Image"

    def select_color(self, image, red=255, green=255, blue=255, variance=10):
    
        if 'opencv-python' not in packages():
            print("\033[34mWAS NS:\033[0m Installing CV2...")
            subprocess.check_call([sys.executable, '-m', 'pip', '-q', 'install', 'opencv-python'])
        
        image = self.color_pick(tensor2pil(image), red, green, blue, variance)
        
        return ( pil2tensor(image), )
        

    def color_pick(self, image, red=255, green=255, blue=255, variance=10):
        # Convert image to RGB mode
        image = image.convert('RGB')

        # Create a new black image of the same size as the input image
        selected_color = Image.new('RGB', image.size, (0,0,0))

        # Get the width and height of the image
        width, height = image.size

        # Loop through every pixel in the image
        for x in range(width):
            for y in range(height):
                # Get the color of the pixel
                pixel = image.getpixel((x,y))
                r,g,b = pixel

                # Check if the pixel is within the specified color range
                if ((r >= red-variance) and (r <= red+variance) and
                    (g >= green-variance) and (g <= green+variance) and
                    (b >= blue-variance) and (b <= blue+variance)):
                    # Set the pixel in the selected_color image to the RGB value of the pixel
                    selected_color.putpixel((x,y),(r,g,b))

        # Return the selected color image
        return selected_color
       
# IMAGE CONVERT TO CHANNEL
        
class WAS_Image_Select_Channel:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "channel": (['red','green','blue'],),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "select_channel"

    CATEGORY = "WAS Suite/Image"

    def select_channel(self, image, channel='red'):
        
        image = self.convert_to_single_channel(tensor2pil(image), channel)
        
        return ( pil2tensor(image), )
        

    def convert_to_single_channel(self, image, channel='red'):
        
        # Convert to RGB mode to access individual channels
        image = image.convert('RGB')

        # Extract the desired channel and convert to greyscale
        if channel == 'red':
            channel_img = image.split()[0].convert('L')
        elif channel == 'green':
            channel_img = image.split()[1].convert('L')
        elif channel == 'blue':
            channel_img = image.split()[2].convert('L')
        else:
            raise ValueError("Invalid channel option. Please choose 'red', 'green', or 'blue'.")

        # Convert the greyscale channel back to RGB mode
        channel_img = Image.merge('RGB', (channel_img, channel_img, channel_img))

        return channel_img
        
        
        
# IMAGE CONVERT TO CHANNEL
        
class WAS_Image_RGB_Merge:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "red_channel": ("IMAGE",),
                "green_channel": ("IMAGE",),
                "blue_channel": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "merge_channels"

    CATEGORY = "WAS Suite/Image"

    def merge_channels(self, red_channel, green_channel, blue_channel):
        
        # Apply mix rgb channels
        image = self.mix_rgb_channels(tensor2pil(red_channel).convert('L'), tensor2pil(green_channel).convert('L'), tensor2pil(blue_channel).convert('L'))
        
        return ( pil2tensor(image), )
        

    def mix_rgb_channels(self, red, green, blue):
        # Create an empty image with the same size as the channels
        width, height = red.size; merged_img = Image.new('RGB', (width, height))

        # Merge the channels into the new image
        merged_img = Image.merge('RGB', (red, green, blue))

        return merged_img
        

# Image Save (NSP Compatible)
# Originally From ComfyUI/nodes.py
        
class WAS_Image_Save:
    def __init__(self):
        self.output_dir = os.path.join(os.getcwd()+'/ComfyUI', "output")

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": {
                        "images": ("IMAGE", ),
                        "output_path": ("STRING", {"default": './ComfyUI/output', "multiline": False}),
                        "filename_prefix": ("STRING", {"default": "ComfyUI"}),
                        "extension": (['png', 'jpeg', 'tiff', 'gif'], ),
                        "quality": ("INT", {"default": 100, "min": 1, "max": 100, "step": 1}),
                    },
                    "hidden": {
                        "prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"
                    },
                }

    RETURN_TYPES = ()
    FUNCTION = "save_images"

    OUTPUT_NODE = True

    CATEGORY = "WAS Suite/IO"

    def save_images(self, images, output_path='', filename_prefix="ComfyUI", extension='png', quality=100, prompt=None, extra_pnginfo=None):
        def map_filename(filename):
            prefix_len = len(filename_prefix)
            prefix = filename[:prefix_len + 1]
            try:
                digits = int(filename[prefix_len + 1:].split('_')[0])
            except:
                digits = 0
            return (digits, prefix)
        
        # Setup custom path or default
        if output_path.strip() != '':
            if not os.path.exists(output_path.strip()):
                print(f'\033[34mWAS NS\033[0m Error: The path `{output_path.strip()}` specified doesn\'t exist! Defaulting to `{self.output_dir}` directory.')
            else:
                self.output_dir = os.path.normpath(output_path.strip())
        
        # Define counter for files found
        try:
            counter = max(filter(lambda a: a[1][:-1] == filename_prefix and a[1][-1] == "_", map(map_filename, os.listdir(self.output_dir))))[0] + 1
        except ValueError:
            counter = 1
        except FileNotFoundError:
            os.mkdir(self.output_dir)
            counter = 1

        paths = list()
        for image in images:
            i = 255. * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
            metadata = PngInfo()
            if prompt is not None:
                metadata.add_text("prompt", json.dumps(prompt))
            if extra_pnginfo is not None:
                for x in extra_pnginfo:
                    metadata.add_text(x, json.dumps(extra_pnginfo[x]))
            file = f"{filename_prefix}_{counter:05}_.{extension}"
            if extension == 'png':
                img.save(os.path.join(self.output_dir, file), pnginfo=metadata, optimize=True)
            elif extension == 'webp':
                img.save(os.path.join(self.output_dir, file), quality=quality)
            elif extension == 'jpeg':
                img.save(os.path.join(self.output_dir, file), quality=quality, optimize=True)
            elif extension == 'tiff':
                img.save(os.path.join(self.output_dir, file), quality=quality, optimize=True)
            else:
                img.save(os.path.join(self.output_dir, file))
            paths.append(file)
            counter += 1
        return { "ui": { "images": paths } }
        
        

# LOAD IMAGE NODE
class WAS_Load_Image:

    def __init__(self):
        self.input_dir = os.path.join(os.getcwd()+'/ComfyUI', "input")
        
    @classmethod
    def INPUT_TYPES(s):
        return {"required":
                    {"image_path": ("STRING", {"default": './ComfyUI/input/example.png', "multiline": False}),}
                }

    CATEGORY = "WAS Suite/IO"

    RETURN_TYPES = ("IMAGE", "MASK")
    FUNCTION = "load_image"
    def load_image(self, image_path):
    
        if image_path.startswith('http'):
            from io import BytesIO
            i = download_image(image_path)
        else:
            try:
                i = Image.open(image_path)
            except OSError:
                print(f'\033[34mWAS NS\033[0m Error: The image `{output_path.strip()}` specified doesn\'t exist!')
                i = Image.new(mode='RGB', size=(512,512), color=(0,0,0))
                
        image = i
        image = np.array(image).astype(np.float32) / 255.0
        image = torch.from_numpy(image)[None,]
        
        if 'A' in i.getbands():
            mask = np.array(i.getchannel('A')).astype(np.float32) / 255.0
            mask = 1. - torch.from_numpy(mask)
        else:
            mask = torch.zeros((64,64), dtype=torch.float32, device="cpu")
        return ( image, mask )

    def download_image(self, url):
        try:
            response = requests.get(url)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content))
            return img
        except requests.exceptions.HTTPError as errh:
            print(f"\033[34mWAS NS\033[0m Error: HTTP Error: ({url}): {errh}") 
        except requests.exceptions.ConnectionError as errc:
            print(f"\033[34mWAS NS\033[0m Error: Connection Error: ({url}): {errc}")  
        except requests.exceptions.Timeout as errt:
            print(f"\033[34mWAS NS\033[0m Error: Timeout Error: ({url}): {errt}")
        except requests.exceptions.RequestException as err:
            print(f"\033[34mWAS NS\033[0m Error: Request Exception: ({url}): {err}")
        
    @classmethod
    def IS_CHANGED(s, image_path):
        if image_path.startswith('http'):
            return True
        m = hashlib.sha256()
        with open(image_path, 'rb') as f:
            m.update(f.read())
        return m.digest().hex()
        

# TENSOR TO IMAGE NODE

class WAS_Tensor_Batch_to_Image:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images_batch": ("IMAGE",),
                "batch_image_number": ("INT", {"default": 0, "min": 0, "max": 64, "step": 1}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "tensor_batch_to_image"

    CATEGORY = "WAS Suite/Latent"

    def tensor_batch_to_image(self, images_batch=None, batch_image_number=0):
    
        count = 0
        for _ in images_batch:
            if batch_image_number == count:
                return ( images_batch[batch_image_number].unsqueeze(0), )
            count = count+1
        
        print(f"\033[34mWAS NS\033[0m Error: Batch number `{batch_image_number}` is not defined, returning last image")
        return( images_batch[-1].unsqueeze(0), )


#! LATENT NODES

# IMAGE TO MASK

class WAS_Image_To_Mask:

    def __init__(s):
        pass
        
    @classmethod
    def INPUT_TYPES(s):
        return {"required":
                    {"image": ("IMAGE",),
                    "channel": (["alpha", "red", "green", "blue"], ),}
                }

    CATEGORY = "WAS Suite/Latent"

    RETURN_TYPES = ("MASK",)
    
    FUNCTION = "image_to_mask"
    
    def image_to_mask(self, image, channel):
    
        img = tensor2pil(image)
        
        mask = None
        c = channel[0].upper()
        if c in img.getbands():
            mask = np.array(img.getchannel(c)).astype(np.float32) / 255.0
            mask = torch.from_numpy(mask)
            if c == 'A':
                mask = 1. - mask
        else:
            mask = torch.zeros((64,64), dtype=torch.float32, device="cpu")
            
        return ( mask, )


# LATENT UPSCALE NODE

class WAS_Latent_Upscale:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {"required": { "samples": ("LATENT",), "mode": (["bilinear", "bicubic"],),
                              "factor": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 8.0, "step": 0.1}),
                              "align": (["true", "false"], )}}
    RETURN_TYPES = ("LATENT",)
    FUNCTION = "latent_upscale"

    CATEGORY = "WAS Suite/Latent"

    def latent_upscale(self, samples, mode, factor, align):
        s = samples.copy()
        s["samples"] = torch.nn.functional.interpolate(s['samples'], scale_factor=factor, mode=mode, align_corners=( True if align == 'true' else False ))
        return (s,)
        
# LATENT NOISE INJECTION NODE
        
class WAS_Latent_Noise:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": {
                        "samples": ("LATENT",), 
                        "noise_std": ("FLOAT", {"default": 0.1, "min": 0.0, "max": 1.0, "step": 0.01}),
                    }
                }

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "inject_noise"
    
    CATEGORY = "WAS Suite/Latent"

    def inject_noise(self, samples, noise_std):
        s = samples.copy()
        noise = torch.randn_like(s["samples"]) * noise_std
        s["samples"] = s["samples"] + noise
        return (s,)
        
        
# MIDAS DEPTH APPROXIMATION NODE

class MiDaS_Depth_Approx:
    def __init__(self):
        self.midas_dir = os.path.join(os.getcwd()+'/ComfyUI', "models/midas")

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "use_cpu": (["false", "true"],),
                "midas_model": (["DPT_Large", "DPT_Hybrid", "DPT_Small"],),
                "invert_depth": (["false", "true"],),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "midas_approx"
    
    CATEGORY = "WAS Suite/Image"

    def midas_approx(self, image, use_cpu, midas_model, invert_depth):
    
        global MIDAS_INSTALLED
 
        if not MIDAS_INSTALLED:
            self.install_midas()
            
        import cv2 as cv
    
        # Convert the input image tensor to a PIL Image
        i = 255. * image.cpu().numpy().squeeze()
        img = i

        print("\033[34mWAS NS:\033[0m Downloading and loading MiDaS Model...")
        torch.hub.set_dir(self.midas_dir)
        midas = torch.hub.load("intel-isl/MiDaS", midas_model, trust_repo=True)
        device = torch.device("cuda") if torch.cuda.is_available() and use_cpu == 'false' else torch.device("cpu")
        
        print('\033[34mWAS NS:\033[0m MiDaS is using device:', device)

        midas.to(device).eval()
        midas_transforms = torch.hub.load("intel-isl/MiDaS", "transforms")

        if midas_model == "DPT_Large" or midas_model == "DPT_Hybrid":
            transform = midas_transforms.dpt_transform
        else:
            transform = midas_transforms.small_transform

        img = cv.cvtColor(img, cv.COLOR_BGR2RGB)
        input_batch = transform(img).to(device)
        
        print('\033[34mWAS NS:\033[0m Approximating depth from image.')

        with torch.no_grad():
            prediction = midas(input_batch)
            prediction = torch.nn.functional.interpolate(
                prediction.unsqueeze(1),
                size=img.shape[:2],
                mode="bicubic",
                align_corners=False,
            ).squeeze()

        # Invert depth map
        if invert_depth == 'true':
            depth = ( 255 - prediction.cpu().numpy().astype(np.uint8) )
            depth = depth.astype(np.float32)
        else:
            depth = prediction.cpu().numpy().astype(np.float32)
        #depth = depth * 255 / (np.max(depth)) / 255
        depth = (depth - depth.min()) / (depth.max() - depth.min())  # Normalize depth to range [0, 1]
        
        # depth to RGB
        depth = cv.cvtColor(depth, cv.COLOR_GRAY2RGB)
        
        tensor = torch.from_numpy( depth )[None,]
        tensors = ( tensor, )

        del midas, device, midas_transforms
        del transform, img, input_batch, prediction
        
        return  tensors
        
    def install_midas(self):
        global MIDAS_INSTALLED
        if 'timm' not in packages():
            print("\033[34mWAS NS:\033[0m Installing timm...")
            subprocess.check_call([sys.executable, '-m', 'pip', '-q', 'install', 'timm'])
        if 'opencv-python' not in packages():
            print("\033[34mWAS NS:\033[0m Installing CV2...")
            subprocess.check_call([sys.executable, '-m', 'pip', '-q', 'install', 'opencv-python'])
        MIDAS_INSTALLED = True        
        
# MIDAS REMOVE BACKGROUND/FOREGROUND NODE

class MiDaS_Background_Foreground_Removal:
    def __init__(self):
        self.midas_dir = os.path.join(os.getcwd()+'/ComfyUI', "models/midas")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "use_cpu": (["false", "true"],),
                "midas_model": (["DPT_Large", "DPT_Hybrid", "DPT_Small"],),
                "remove": (["background", "foregroud"],),
                "threshold": (["false", "true"],),
                "threshold_low": ("FLOAT", {"default": 10, "min": 0, "max": 255, "step": 1}),
                "threshold_mid": ("FLOAT", {"default": 200, "min": 0, "max": 255, "step": 1}),
                "threshold_high": ("FLOAT", {"default": 210, "min": 0, "max": 255, "step": 1}),
                "smoothing": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 16.0, "step": 0.01}),
                "background_red": ("INT", {"default": 0, "min": 0, "max": 255, "step": 1}),
                "background_green": ("INT", {"default": 0, "min": 0, "max": 255, "step": 1}),
                "background_blue": ("INT", {"default": 0, "min": 0, "max": 255, "step": 1}),
            },
        }

    RETURN_TYPES = ("IMAGE","IMAGE")
    FUNCTION = "midas_remove"
    
    CATEGORY = "WAS Suite/Image"

    def midas_remove(self,
                    image,  
                    midas_model,
                    use_cpu='false',                    
                    remove='background', 
                    threshold='false',
                    threshold_low=0,
                    threshold_mid=127,
                    threshold_high=255,
                    smoothing=0.25,
                    background_red=0, 
                    background_green=0, 
                    background_blue=0):
    
        global MIDAS_INSTALLED
 
        if not MIDAS_INSTALLED:
            self.install_midas()
            
        import cv2 as cv
    
        # Convert the input image tensor to a numpy and PIL Image
        i = 255. * image.cpu().numpy().squeeze()
        img = i
        # Original image
        img_original = tensor2pil(image).convert('RGB')

        print("\033[34mWAS NS:\033[0m Downloading and loading MiDaS Model...")
        torch.hub.set_dir(self.midas_dir)
        midas = torch.hub.load("intel-isl/MiDaS", midas_model, trust_repo=True)
        device = torch.device("cuda") if torch.cuda.is_available() and use_cpu == 'false' else torch.device("cpu")
        
        print('\033[34mWAS NS:\033[0m MiDaS is using device:', device)

        midas.to(device).eval()
        midas_transforms = torch.hub.load("intel-isl/MiDaS", "transforms")

        if midas_model == "DPT_Large" or midas_model == "DPT_Hybrid":
            transform = midas_transforms.dpt_transform
        else:
            transform = midas_transforms.small_transform

        img = cv.cvtColor(img, cv.COLOR_BGR2RGB)
        input_batch = transform(img).to(device)
        
        print('\033[34mWAS NS:\033[0m Approximating depth from image.')

        with torch.no_grad():
            prediction = midas(input_batch)
            prediction = torch.nn.functional.interpolate(
                prediction.unsqueeze(1),
                size=img.shape[:2],
                mode="bicubic",
                align_corners=False,
            ).squeeze()

        # Invert depth map
        if remove == 'foreground':
            depth = ( 255 - prediction.cpu().numpy().astype(np.uint8) )
            depth = depth.astype(np.float32)
        else:
            depth = prediction.cpu().numpy().astype(np.float32)
        depth = depth * 255 / (np.max(depth)) / 255
        depth = Image.fromarray(np.uint8(depth * 255))
        
        # Threshold depth mask
        if threshold == 'true':
            levels = self.AdjustLevels(threshold_low, threshold_mid, threshold_high)
            depth = levels.adjust(depth.convert('RGB')).convert('L')
        if smoothing > 0:
            depth = depth.filter(ImageFilter.GaussianBlur(radius=smoothing))
        depth = depth.resize(img_original.size).convert('L')
        
        # Validate background color arguments
        background_red = int(background_red) if isinstance(background_red, (int, float)) else 0
        background_green = int(background_green) if isinstance(background_green, (int, float)) else 0
        background_blue = int(background_blue) if isinstance(background_blue, (int, float)) else 0

        # Create background color tuple
        background_color = ( background_red, background_green, background_blue )
        
        # Create background image
        background = Image.new(mode="RGB", size=img_original.size, color=background_color)
        
        # Composite final image
        result_img = Image.composite(img_original, background, depth)

        del midas, device, midas_transforms
        del transform, img, img_original, input_batch, prediction
        
        return ( pil2tensor(result_img), pil2tensor(depth.convert('RGB')) )     
        
    class AdjustLevels:
        def __init__(self, min_level, mid_level, max_level):
            self.min_level = min_level
            self.mid_level = mid_level
            self.max_level = max_level

        def adjust(self, im):
            # load the image

            # convert the image to a numpy array
            im_arr = np.array(im)

            # apply the min level adjustment
            im_arr[im_arr < self.min_level] = self.min_level

            # apply the mid level adjustment
            im_arr = (im_arr - self.min_level) * (255 / (self.max_level - self.min_level))
            im_arr[im_arr < 0] = 0
            im_arr[im_arr > 255] = 255
            im_arr = im_arr.astype(np.uint8)

            # apply the max level adjustment
            im = Image.fromarray(im_arr)
            im = ImageOps.autocontrast(im, cutoff=self.max_level)

            return im
        
    def install_midas(self):
        global MIDAS_INSTALLED
        if 'timm' not in packages():
            print("\033[34mWAS NS:\033[0m Installing timm...")
            subprocess.check_call([sys.executable, '-m', 'pip', '-q', 'install', 'timm'])
        if 'opencv-python' not in packages():
            print("\033[34mWAS NS:\033[0m Installing CV2...")
            subprocess.check_call([sys.executable, '-m', 'pip', '-q', 'install', 'opencv-python'])
        MIDAS_INSTALLED = True


#! CONDITIONING NODES


# NSP CLIPTextEncode NODE

class WAS_NSP_CLIPTextEncoder:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": {
                            "noodle_key": ("STRING", {"default": '__', "multiline": False}),
                            "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                            "text": ("STRING", {"multiline": True}),
                            "clip": ("CLIP",),
                    }
                }
    
    OUTPUT_NODE = True
    RETURN_TYPES = ("CONDITIONING",)
    FUNCTION = "nsp_encode"

    CATEGORY = "WAS Suite/Conditioning"

    def nsp_encode(self, clip, text, noodle_key = '__', seed = 0):
    
        # Fetch the NSP Pantry
        local_pantry = os.getcwd()+'/ComfyUI/custom_nodes/nsp_pantry.json'
        if not os.path.exists(local_pantry):
            response = urlopen('https://raw.githubusercontent.com/WASasquatch/noodle-soup-prompts/main/nsp_pantry.json')
            tmp_pantry = json.loads(response.read())
            # Dump JSON locally
            pantry_serialized = json.dumps(tmp_pantry, indent=4)
            with open(local_pantry, "w") as f:
                f.write(pantry_serialized)
            del response, tmp_pantry
        
        # Load local pantry
        with open(local_pantry, 'r') as f:
            nspterminology = json.load(f)
            
        if seed > 0 or seed < 1:
            random.seed(seed)
            
        # Parse Text
        new_text = text
        for term in nspterminology:
            # Target Noodle
            tkey = f'{noodle_key}{term}{noodle_key}'
            # How many occurances?
            tcount = new_text.count(tkey)
            # Apply random results for each noodle counted
            for _ in range(tcount):
                new_text = new_text.replace(tkey, random.choice(nspterminology[term]), 1)
                seed = seed+1
                random.seed(seed)
                
        print('\033[34mWAS NS\033[0m CLIPTextEncode NSP:', new_text)
        
        return ([[clip.encode(new_text), {}]],{"ui":{"prompt":new_text}})


#! SAMPLING NODES

# KSAMPLER

class WAS_KSampler:
    @classmethod
    def INPUT_TYPES(s):
        return {"required":
                    {"model": ("MODEL",),
                    "seed": ("SEED",),
                    "steps": ("INT", {"default": 20, "min": 1, "max": 10000}),
                    "cfg": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0}),
                    "sampler_name": (comfy.samplers.KSampler.SAMPLERS, ),
                    "scheduler": (comfy.samplers.KSampler.SCHEDULERS, ),
                    "positive": ("CONDITIONING", ),
                    "negative": ("CONDITIONING", ),
                    "latent_image": ("LATENT", ),
                    "denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                    }
                }

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "sample"

    CATEGORY = "WAS Suite/Sampling"

    def sample(self, model, seed, steps, cfg, sampler_name, scheduler, positive, negative, latent_image, denoise=1.0):
        return nodes.common_ksampler(model, seed['seed'], steps, cfg, sampler_name, scheduler, positive, negative, latent_image, denoise=denoise)

# SEED NODE
        
class WAS_Seed:
    @classmethod
    def INPUT_TYPES(s):
        return {"required":
                    {"seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff})}
                }


    RETURN_TYPES = ("SEED",)
    FUNCTION = "seed"

    CATEGORY = "WAS Suite/Constant"

    def seed(self, seed):
        return ( {"seed": seed,}, )
    

#! TEXT NODES

# Text Multiline Node

class WAS_Text_Multiline:
    def __init__(s):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": { 
                        "text": ("STRING", {"default": '', "multiline": True}),
                    }
                }
    RETURN_TYPES = ("ASCII",)
    FUNCTION = "text_multiline"

    CATEGORY = "WAS Suite/Text"

    def text_multiline(self, text):
        return ( text, )
        
        
# Text String Node

class WAS_Text_String:
    def __init__(s):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": { 
                        "text": ("STRING", {"default": '', "multiline": False}),
                    }
                }
    RETURN_TYPES = ("ASCII",)
    FUNCTION = "text_string"

    CATEGORY = "WAS Suite/Text"

    def text_string(self, text):
        return ( text, )


# Text Random Line

class WAS_Text_Random_Line:
    def __init__(s):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": {
                        "text": ("ASCII",),
                        "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                    }
                }
                
    RETURN_TYPES = ("ASCII",)
    FUNCTION = "text_random_line"

    CATEGORY = "WAS Suite/Text"

    def text_random_line(self, text, seed):
        lines = text.split("\n")
        random.seed(seed)
        choice = random.choice(lines)
        return ( choice, )


# Text Concatenate      
        
class WAS_Text_Concatenate:
    def __init__(s):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": {
                        "text_a": ("ASCII",),
                        "text_b": ("ASCII",),
                        "linebreak_addition": (['true','false'], ),
                    }
                }
                
    RETURN_TYPES = ("ASCII",)
    FUNCTION = "text_concatenate"

    CATEGORY = "WAS Suite/Text"

    def text_concatenate(self, text_a, text_b, linebreak_addition):
        return ( text_a + ("\n" if linebreak_addition == 'true' else '') + text_b, )
        

# Text Search and Replace  
        
class WAS_Search_and_Replace:
    def __init__(s):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": {
                        "text": ("ASCII",),
                        "find": ("STRING", {"default": '', "multiline": False}),
                        "replace": ("STRING", {"default": '', "multiline": False}),
                    }
                }
                
    RETURN_TYPES = ("ASCII",)
    FUNCTION = "text_search_and_replace"

    CATEGORY = "WAS Suite/Text"

    def text_search_and_replace(self, text, find, replace):
        return ( self.replace_substring(text, find, replace), )
        
    def replace_substring(self, text, find, replace):
        import re
        text = re.sub(find, replace, text)
        return text
        

# Text Search and Replace  
        
class WAS_Search_and_Replace_Input:
    def __init__(s):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": {
                        "text": ("ASCII",),
                        "find": ("ASCII",),
                        "replace": ("ASCII",),
                    }
                }
                
    RETURN_TYPES = ("ASCII",)
    FUNCTION = "text_search_and_replace"

    CATEGORY = "WAS Suite/Text"

    def text_search_and_replace(self, text, find, replace):
        return ( self.replace_substring(text, find, replace), )
        
    def replace_substring(self, text, find, replace):
        import re
        text = re.sub(find, replace, text)
        return text
        
        
# Text Parse NSP
        
class WAS_Text_Parse_NSP:
    def __init__(s):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": {
                            "noodle_key": ("STRING", {"default": '__', "multiline": False}),
                            "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                            "text": ("ASCII",),
                    }
                }
    
    OUTPUT_NODE = True
    RETURN_TYPES = ("ASCII",)
    FUNCTION = "text_parse_nsp"

    CATEGORY = "WAS Suite/Text"

    def text_parse_nsp(self, text, noodle_key = '__', seed = 0):
    
        # Fetch the NSP Pantry
        local_pantry = os.getcwd()+'/ComfyUI/custom_nodes/nsp_pantry.json'
        if not os.path.exists(local_pantry):
            response = urlopen('https://raw.githubusercontent.com/WASasquatch/noodle-soup-prompts/main/nsp_pantry.json')
            tmp_pantry = json.loads(response.read())
            # Dump JSON locally
            pantry_serialized = json.dumps(tmp_pantry, indent=4)
            with open(local_pantry, "w") as f:
                f.write(pantry_serialized)
            del response, tmp_pantry
        
        # Load local pantry
        with open(local_pantry, 'r') as f:
            nspterminology = json.load(f)
            
        if seed > 0 or seed < 1:
            random.seed(seed)
            
        # Parse Text
        new_text = text
        for term in nspterminology:
            # Target Noodle
            tkey = f'{noodle_key}{term}{noodle_key}'
            # How many occurances?
            tcount = new_text.count(tkey)
            # Apply random results for each noodle counted
            for _ in range(tcount):
                new_text = new_text.replace(tkey, random.choice(nspterminology[term]), 1)
                seed = seed+1
                random.seed(seed)
                
        print('\033[34mWAS NS\033[0m Text Parse NSP:', new_text)
        
        return ( new_text, )
        
        
# TEXT SEARCH AND REPLACE
        
class WAS_Text_Save:
    def __init__(s):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": {
                        "text": ("ASCII",),
                        "path": ("STRING", {"default": '', "multiline": False}),
                        "filename": ("STRING", {"default": f'text_[time]', "multiline": False}),
                    }
                }
                
    OUTPUT_NODE = True
    RETURN_TYPES = ()
    FUNCTION = "save_text_file"

    CATEGORY = "WAS Suite/IO"

    def save_text_file(self, text, path, filename):
        
        # Ensure path exists
        if not os.path.exists(path):
            print(f'\033[34mWAS NS\033[0m Error: The path `{path}` doesn\'t exist!')
            
        # Ensure content to save
        if text.strip == '':
            print(f'\033[34mWAS NS\033[0m Error: There is no text specified to save! Text is empty.')
            
        # Replace tokens
        tokens = {
                    '[time]': f'{round(time.time())}',
                }
        for k in tokens.keys():
            text = self.replace_substring(text, k, tokens[k])
            
        # Write text file
        self.writeTextFile(os.path.join(path, filename + '.txt'), text)
        
        return( text, )
        
    # Save Text FileNotFoundError
    def writeTextFile(self, file, content):
        try:
            with open(file, 'w') as f:
                f.write(content)
        except OSError:
            print(f'\033[34mWAS Node Suite\033[0m Error: Unable to save file `{file}`')
            
            
    # Replace a substring
    def replace_substring(self, text, find, replace):
        import re
        text = re.sub(find, replace, text)
        return text

        
# TEXT TO CONDITIONIONG

class WAS_Text_to_Conditioning:
    def __init__(s):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": {
                        "clip": ("CLIP",),
                        "text": ("ASCII",),
                    }
                }
                
    RETURN_TYPES = ("CONDITIONING",)
    FUNCTION = "text_to_conditioning"

    CATEGORY = "WAS Suite/Text"

    def text_to_conditioning(self, clip, text):
        return ( [[clip.encode(text), {}]], )
        
        
class WAS_Text_to_Console:
    def __init__(s):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": {
                        "text": ("ASCII",),
                        "label": ("STRING", {"default": f'Text Output', "multiline": False}),
                    }
                }
                
    RETURN_TYPES = ("ASCII",)
    OUTPUT_NODE = True
    FUNCTION = "text_to_console"

    CATEGORY = "WAS Suite/Text"

    def text_to_console(self, text, label):
        if label.strip() != '':
            print(f'\033[34mWAS Node Suite \033[33m{label}\033[0m:\n{text}\n')
        else:
            print(f'\033[34mWAS Node Suite \033[33mText to Console\033[0m:\n{text}\n')
        return ( text, )



# LOAD TEXT FILE   

class WAS_Text_Load_From_File:
    def __init__(s):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": {
                        "file_path": ("STRING", {"default": '', "multiline": False}),
                    }
                }
                
    RETURN_TYPES = ("ASCII",)
    FUNCTION = "load_file"

    CATEGORY = "WAS Suite/IO"

    def load_file(self, file_path=''):
        return ( self.load_text_file(file_path), )
    
    def load_text_file(self, path):
        if not os.path.exists(path):
            print(f'\033[34mWAS Node Suite\033[0m Error: The path `{file}` specified cannot be found.')
            return ''
        with open(path, 'r') as file:
            text = file.read()
        return text
         


#! NUMBERS


# RANDOM NUMBER

class WAS_Random_Number:
    def __init__(s):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": {
                        "number_type": (["integer","float","bool"],),
                        "minimum": ("FLOAT", {"default": 0, "min": 0xffffffffffffffff, "max": 0xffffffffffffffff}),
                        "maximum": ("FLOAT", {"default": 0, "min": 0xffffffffffffffff, "max": 0xffffffffffffffff}),
                        "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                    }
                }
                
    RETURN_TYPES = ("NUMBER",)
    FUNCTION = "return_randm_number"

    CATEGORY = "WAS Suite/Constant"

    def return_randm_number(self, minimum, maximum, seed, number_type='integer'):
    
        # Set Generator Seed
        random.seed(seed)
        
        # Return random number
        match number_type:
            case 'integer':
                number = random.randint(minimum, maximum)
            case 'float':
                number = random.uniform(minimum, maximum)
            case 'bool':
                number = random.random()
            
        # Return number
        return ( number, )



# CONSTANT NUMBER

class WAS_Constant_Number:
    def __init__(s):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": {
                        "number_type": (["integer","float","bool"],),
                        "number": ("FLOAT", {"default": 0, "min": 0xffffffffffffffff, "max": 0xffffffffffffffff}),
                    }
                }
                
    RETURN_TYPES = ("NUMBER",)
    FUNCTION = "return_constant_number"

    CATEGORY = "WAS Suite/Constant"

    def return_constant_number(self, number_type, number):
    
        # Return number
        match number_type:
            case 'integer':
                return ( int(number), )
            case 'integer':
                return ( float(number), )
            case 'bool':
                return ( ( 1 if int(number) > 0 else 0 ), )



# NUMBER TO SEED

class WAS_Number_To_Seed:
    def __init__(s):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": {
                        "number": ("NUMBER",),
                    }
                }
                
    RETURN_TYPES = ("SEED",)
    FUNCTION = "number_to_seed"

    CATEGORY = "WAS Suite/Constant"

    def return_constant_number(self, number):
        return ( {"seed":number,}, )

        
        
      
# NUMBER OPERATIONS
        
class WAS_Number_Operation:
    def __init__(s):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": {
                        "number_a": ("NUMBER",),
                        "number_b": ("NUMBER",),
                        "operation": (["addition","subtraction","division","floor division","multiplication","exponentiation","modulus","greater-than","greater-than or equels","less-than","less-than or equals","equals","does not equal"],),
                    }
                }
                
    RETURN_TYPES = ("NUMBER",)
    FUNCTION = "math_operations"

    CATEGORY = "WAS Suite/Operations"

    def math_operations(self, number_a, number_b, operation="addition"):
        
        # Return random number
        match operation:
            case 'addition':
                return ( (number_a + number_b), )
            case 'subtraction':
                return ( (number_a - number_b), )
            case 'division':
                return ( (number_a / number_b), )
            case 'floor division':
                return ( (number_a // number_b), )
            case 'multiplication':
                return ( (number_a * number_b), )
            case 'exponentiation':
                return ( (number_a ** number_b), )
            case 'modulus':
                return ( (number_a % number_b), )
            case 'greater-than':
                return ( +(number_a > number_b), )
            case 'greater-than or equals':
                return ( +(number_a >= number_b), )
            case 'less-than':
                return ( +(number_a < number_b), )
            case 'less-than or equals':
                return ( +(number_a <= number_b), )
            case 'equals':
                return ( +(number_a == number_b), )
            case 'does not equal':
                return ( +(number_a != number_b), )
              

#! MISC              
                
               
# INPUT SWITCH
                
class WAS_Input_Switch:
    def __init__(s):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": {
                        "input_a": ("*",),
                        "input_b": ("*",),
                        "boolean": ("NUMBER",),
                    }
                }
                
    RETURN_TYPES = ("*",)
    FUNCTION = "input_switch"

    CATEGORY = "WAS Suite/Operations"

    def input_switch(self, input_a, input_b, boolean=0):
        
        if int(boolean) == 1:
            return ( input_a, )
        else:
            return ( input_b, )
            
            

# DEBUG INPUT TO CONSOLE
        
        
class WAS_Debug_to_Console:
    def __init__(s):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
                    "required": {
                        "debug_input": ("*",),
                        "label": ("STRING", {"default": f'Debug Input', "multiline": False}),
                    }
                }
     
    RETURN_TYPES = ("*",)
    OUTPUT_NODE = True
    FUNCTION = "debug_to_console"

    CATEGORY = "WAS Suite/Debug"

    def debug_to_console(self, label, debug_input=None):
        if label.strip() != '':
            print(f'\033[34mWAS Node Suite \033[33m{label}\033[0m:\n{text}\n')
        else:
            print(f'\033[34mWAS Node Suite \033[33mDebug to Console\033[0m:\n{text}\n')
        return ( debug_input, )
            



# NODE MAPPING

NODE_CLASS_MAPPINGS = {
    "CLIPTextEncode (NSP)": WAS_NSP_CLIPTextEncoder,
    "Constant Number": WAS_Constant_Number,
    "Debug to Console": WAS_Debug_to_Console,
    "Image Blank": WAS_Image_Blank,
    "Image Blend by Mask": WAS_Image_Blend_Mask,
    "Image Blend": WAS_Image_Blend,
    "Image Blending Mode": WAS_Image_Blending_Mode,
    "Image Bloom Filter": WAS_Image_Bloom_Filter,
    "Image Canny Filter": WAS_Canny_Filter,
    "Image Chromatic Aberration": WAS_Image_Chromatic_Aberration,
    "Image Edge Detection Filter": WAS_Image_Edge,
    "Image Film Grain": WAS_Film_Grain,
    "Image Filter Adjustments": WAS_Image_Filters,
    "Image Flip": WAS_Image_Flip,
    "Image High Pass Filter": WAS_Image_High_Pass_Filter,
    "Image Levels Adjustment": WAS_Image_Levels,
    "Image Load": WAS_Load_Image,
    "Image Median Filter": WAS_Image_Median_Filter,
    "Image Mix RGB Channels": WAS_Image_RGB_Merge,
    "Image Nova Filter": WAS_Image_Nova_Filter,
    "Image Padding": WAS_Image_Padding,
    "Image Remove Color": WAS_Image_Remove_Color,
    "Image Resize": WAS_Image_Rescale,
    "Image Rotate": WAS_Image_Rotate,
    "Image Save": WAS_Image_Save,
    "Image Select Channel": WAS_Image_Select_Channel,
    "Image Select Color": WAS_Image_Select_Color,
    "Image Style Filter": WAS_Image_Style_Filter,
    "Image Threshold": WAS_Image_Threshold,
    "Image Transpose": WAS_Image_Transpose,
    "Image fDOF Filter": WAS_Image_fDOF,
    "Image to Latent Mask": WAS_Image_To_Mask,
    "KSampler (WAS)": WAS_KSampler,
    "Latent Noise Injection": WAS_Latent_Noise,
    "Latent Upscale by Factor (WAS)": WAS_Latent_Upscale,
    "Load Image Batch": WAS_Load_Image_Batch,
    "Load Text File": WAS_Text_Load_From_File,
    "MiDaS Depth Approximation": MiDaS_Depth_Approx,
    "MiDaS Mask Image": MiDaS_Background_Foreground_Removal,
    "Number Operation": WAS_Number_Operation,
    "Number to Seed": WAS_Number_To_Seed,
    "Random Number": WAS_Random_Number,
    "Save Text File": WAS_Text_Save,
    "Seed": WAS_Seed,
    "Tensor Batch to Image": WAS_Tensor_Batch_to_Image,
    "Text Concatenate": WAS_Text_Concatenate,
    "Text Find and Replace Input": WAS_Search_and_Replace_Input,
    "Text Find and Replace": WAS_Search_and_Replace,
    "Text Multiline": WAS_Text_Multiline,
    "Text Parse Noodle Soup Prompts": WAS_Text_Parse_NSP,
    "Text Random Line": WAS_Text_Random_Line,
    "Text String": WAS_Text_String,
    "Text to Conditioning": WAS_Text_to_Conditioning,
    "Text to Console": WAS_Text_to_Console,
}

print('\033[34mWAS Node Suite: \033[92mLoaded\033[0m')