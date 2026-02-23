import cv2
import cv2.aruco as aruco

# Define the dictionary
aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)

# Generate and save 4 markers (IDs 0, 1, 2, 3)
for i in range(4):
    img = aruco.generateImageMarker(aruco_dict, i, 300) # 300x300 pixels
    cv2.imwrite(f"marker_{i}.png", img)

print("Success! Saved marker_0.png, marker_1.png, marker_2.png, marker_3.png")