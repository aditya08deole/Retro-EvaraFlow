import matplotlib.pyplot as plt
from matplotlib.widgets import RectangleSelector
import cv2
import json
import os
import numpy as np

# --- CONFIGURATION ---
SAMPLE_IMAGE_PATH = r"data/raw_images/sample75.jpg" 
OUTPUT_CONFIG_FILE = "meter_config.json"

# Target Dimensions for the "Flattened" view
WIDTH, HEIGHT = 650, 215
PTS_DST = np.float32([[0, 0], [WIDTH, 0], [WIDTH, HEIGHT], [0, HEIGHT]])

current_points = []

def line_select_callback(eclick, erelease):
    """
    Callback for line selection.
    eclick: mouse click event
    erelease: mouse release event
    """
    global current_points
    
    # Get coordinates of the box (xmin, xmax, ymin, ymax)
    x1, y1 = eclick.xdata, eclick.ydata
    x2, y2 = erelease.xdata, erelease.ydata
    
    # Sort to ensure we always get Top-Left and Bottom-Right correctly
    xmin = min(x1, x2)
    xmax = max(x1, x2)
    ymin = min(y1, y2)
    ymax = max(y1, y2)
    
    # Create the 4 corners in the exact Z-order the detector expects:
    # TL, TR, BR, BL
    current_points = [
        [int(xmin), int(ymin)], # Top-Left
        [int(xmax), int(ymin)], # Top-Right
        [int(xmax), int(ymax)], # Bottom-Right
        [int(xmin), int(ymax)]  # Bottom-Left
    ]
    
    print(f"Box Selected: {current_points}")
    print("Press 'Q' to Save and Exit.")

def toggle_selector(event):
    if event.key in ['Q', 'q'] and toggle_selector.RS.active:
        print(' RectangleSelector deactivated.')
        toggle_selector.RS.set_active(False)
        
        if len(current_points) == 4:
            save_config()
            # Show final preview
            show_preview()
            plt.close()

def save_config():
    config_data = {
        "node_name": "Hybrid_Node",
        "pts_source": current_points
    }
    with open(OUTPUT_CONFIG_FILE, 'w') as f:
        json.dump(config_data, f)
    print(f"\nSUCCESS! Config saved to {OUTPUT_CONFIG_FILE}")

def show_preview():
    # Helper to show user what the "Flattened" crop looks like
    if not os.path.exists(SAMPLE_IMAGE_PATH): return
    img = cv2.imread(SAMPLE_IMAGE_PATH)
    
    matrix = cv2.getPerspectiveTransform(np.float32(current_points), PTS_DST)
    warped = cv2.warpPerspective(img, matrix, (WIDTH, HEIGHT))
    
    plt.figure()
    plt.imshow(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB))
    plt.title("Saved Crop Preview")
    plt.show()

if __name__ == "__main__":
    if not os.path.exists(SAMPLE_IMAGE_PATH):
        print(f"Error: {SAMPLE_IMAGE_PATH} not found.")
        exit()

    img = cv2.imread(SAMPLE_IMAGE_PATH)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.imshow(img_rgb)
    ax.set_title("Draw a Box around digits. Press 'Q' to Save.")

    # Initialize the Drag Box Selector
    toggle_selector.RS = RectangleSelector(
        ax, line_select_callback,
        useblit=True,
        button=[1],  # Left mouse button only
        minspanx=5, minspany=5,
        spancoords='pixels',
        interactive=True # Allows you to modify the box after drawing
    )

    plt.connect('key_press_event', toggle_selector)
    plt.show()