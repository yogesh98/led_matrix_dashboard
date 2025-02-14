#!/usr/bin/env python3

import sys
from PIL import Image

def xbm_to_image(input_xbm_path, output_image_path):
    """
    Load an XBM file and save it in a different format.
    """
    try:
        # Open the XBM file
        img = Image.open(input_xbm_path)
        
        # Optional: Convert to a certain mode if needed (e.g., 'RGB')
        # img = img.convert('RGB')

        # Save to the desired output format (inferred by extension of output_image_path)
        img.save(output_image_path)
        print(f"Converted XBM '{input_xbm_path}' to '{output_image_path}'.")
        
    except Exception as e:
        print(f"Error converting XBM file: {e}")

def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.xbm> <output.png>")
        sys.exit(1)
    
    input_xbm = sys.argv[1]
    output_image = sys.argv[2]
    
    xbm_to_image(input_xbm, output_image)

if __name__ == '__main__':
    main()
