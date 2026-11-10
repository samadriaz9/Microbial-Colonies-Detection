#!/usr/bin/env python3
import RPi.GPIO as GPIO
import cv2
import threading
import time
import os
import json
from datetime import datetime
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

# ============================================
# Global Camera Instance, Lock, and Preview Setup
# ============================================
video_capture = cv2.VideoCapture(0)
camera_lock = threading.Lock()   # Protects concurrent access to video_capture
latest_frame = None  # For live preview
petri_lock = threading.Lock()    # Protects petri dish counter

base_dir = "experiment_"
new_dir = None  # Created lazily on first capture/save
petri_index = 0  # Increments each time a petri pipeline runs in this GUI session

def ensure_session_dir():
    global new_dir
    if new_dir is not None:
        return new_dir
    i = 1
    while os.path.exists(f"{base_dir}{i}"):
        i += 1
    new_dir = f"{base_dir}{i}"
    os.makedirs(new_dir, exist_ok=True)
    return new_dir

def next_petri_folder_name():
    """Return the next PetriDishXData folder name and increment the counter."""
    global petri_index
    with petri_lock:
        petri_index += 1
        return f"PetriDish{petri_index}Data"

def update_camera():
    """Continuously capture frames from the camera and update the GUI preview."""
    global latest_frame
    with camera_lock:
        ret, frame = video_capture.read()
    if ret:
        latest_frame = frame  # Save the latest raw frame
        # Convert frame from BGR to RGB for display
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        # Create a PIL image from the array
        image = Image.fromarray(frame_rgb)
        imgtk = ImageTk.PhotoImage(image=image)
        camera_label.imgtk = imgtk
        camera_label.configure(image=imgtk)
    root.after(1, update_camera)  # Update roughly every 20ms

# ============================================
# Part 1: Hardware Setup, JSON Motor Logic, & Pipeline Functions
# ============================================

# ----- GPIO & Motor Setup -----
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)

# Motor 1 pins (e.g., horizontal)
MOTOR1_DIR = 37    # Direction
MOTOR1_STEP = 38   # Step
MOTOR1_EN  = 40   # Enable

# Motor 2 pins (e.g., vertical)
MOTOR2_DIR = 11    # Direction
MOTOR2_STEP = 12   # Step
MOTOR2_EN  = 15   # Enable

for pin in (MOTOR1_DIR, MOTOR1_STEP, MOTOR1_EN, MOTOR2_DIR, MOTOR2_STEP, MOTOR2_EN):
    GPIO.setup(pin, GPIO.OUT)
GPIO.output(MOTOR1_EN, GPIO.LOW)  # Enable driver
GPIO.output(MOTOR2_EN, GPIO.LOW)

# ----- JSON-Based Motor Position Logic -----
json_file = "steps.json"
if not os.path.exists(json_file):
    data = {"motor1_steps": 0, "motor2_steps": 0}
    with open(json_file, "w") as f:
        json.dump(data, f)
    motor1_steps = 0
    motor2_steps = 0
else:
    with open(json_file, "r") as f:
        data = json.load(f)
        motor1_steps = data.get("motor1_steps", 0)
        motor2_steps = data.get("motor2_steps", 0)
print("Read from JSON:")
print("  Motor 1 steps:", motor1_steps)
print("  Motor 2 steps:", motor2_steps)

def save_steps():
    data = {"motor1_steps": motor1_steps, "motor2_steps": motor2_steps}
    with open(json_file, "w") as f:
        json.dump(data, f)

# ----- Helper Function: move_motor() -----
def move_motor(steps, step_pin, dir_pin, step_delay=0.001, motor_id=None):
    global motor1_steps, motor2_steps
    # Motor 2 is installed upside down, so reverse its direction logic
    if motor_id == "motor2":
        if steps > 0:
            GPIO.output(dir_pin, GPIO.LOW)  # Reversed for upside-down motor
        else:
            GPIO.output(dir_pin, GPIO.HIGH)  # Reversed for upside-down motor
    else:
        # Normal direction logic for Motor 1
        if steps > 0:
            GPIO.output(dir_pin, GPIO.HIGH)
        else:
            GPIO.output(dir_pin, GPIO.LOW)
    for _ in range(abs(steps)):
        GPIO.output(step_pin, GPIO.HIGH)
        time.sleep(step_delay)
        GPIO.output(step_pin, GPIO.LOW)
        time.sleep(step_delay)
    if motor_id == "motor1":
        motor1_steps += steps
    elif motor_id == "motor2":
        motor2_steps += steps
    save_steps()

# ----- Initialize Motors to Home (0) -----
if motor1_steps == 0 or motor1_steps == 5200:
    pass
else:
    print("Initializing Motor 1 to home (0)...")
    move_motor(-motor1_steps, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
if motor2_steps != 0:
    print("Initializing Motor 2 to home (0)...")
    move_motor(-motor2_steps, MOTOR2_STEP, MOTOR2_DIR, motor_id="motor2")
print("Motors initialized. Current positions saved to JSON.")

# --- Added: On startup, move Motor 1 an extra 6500 steps (i.e. offset) ---
print("Moving Motor 1 to initial offset (6500 steps)...")
#move_motor(6500, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
if motor1_steps == 5200:
    pass
else:
    for i in range(260):
       move_motor(20, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
       print('motor 1 steps: ', motor1_steps)
    
# ----- Function: combine_images() -----
def combine_images(images_dir):
    image_width, image_height = 1920, 1080
    pattern = [
        [1, 14, 15, 28],
        [2, 13, 16, 27],
        [3, 12, 17, 26],
        [4, 11, 18, 25],
        [5, 10, 19, 24],
        [6, 9, 20, 23],
        [7, 8, 21, 22]
    ]
    num_rows = len(pattern)
    num_cols = max(len(row) for row in pattern)
    combined = Image.new('RGB', (num_cols * image_width, num_rows * image_height), color=(0, 0, 0))
    image_dict = {}
    for i in range(1, 29):
        img_path = os.path.join(images_dir, f"{i}.jpg")
        if os.path.exists(img_path):
            try:
                img = Image.open(img_path)
                image_dict[f"{i}.jpg"] = img
            except Exception as e:
                print(f"Error opening {img_path}: {e}")
    for row_idx, row in enumerate(pattern):
        for col_idx, img_num in enumerate(row):
            fname = f"{img_num}.jpg"
            if fname in image_dict:
                combined.paste(image_dict[fname], (col_idx * image_width, row_idx * image_height))
    output_file = os.path.join(images_dir, "combined_image.jpg")
    combined.save(output_file)
    print("Combined image saved as", output_file)

# ----- Pipeline Functions for Petri Dish 1–4 -----
# Note: Each pipeline uses an updated capture_image() that reads directly from the camera.

def run_pipeline_petri1():
    global motor1_steps
    # --- Before pipeline: If Motor 1 is offset, restore it to 0 ---
    if motor1_steps > 0:
        print("Restoring Motor 1 to home before Petri Dish 1 pipeline...")
        #move_motor(-6500, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
        for i in range(20):
            move_motor(-260, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
    
    session_dir = ensure_session_dir()
    dish_folder = next_petri_folder_name()
    images_dir = os.path.join(os.getcwd(), session_dir, dish_folder)
    os.makedirs(images_dir, exist_ok=True)
    
    image_count = 0
    def capture_image(filename):
        
        # Flush the camera buffer and capture a fresh frame.
        with camera_lock:
            for _ in range(5):
                video_capture.grab()
                time.sleep(0.01)
            ret, frame = video_capture.read()
        if ret:
            cv2.imwrite(filename, frame)
            print("Image saved as", filename)
        else:
            print("Failed to capture frame")
    
    print("Petri Dish 1: Moving Motor 2 forward 1 step...")
    move_motor(1, MOTOR2_STEP, MOTOR2_DIR, motor_id="motor2")
    for cycle in range(2):
        time.sleep(0.1)
        for _ in range(6):
            image_count += 1
            filename = os.path.join(images_dir, f"{image_count}.jpg")
            capture_image(filename)
            move_motor(420, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
            time.sleep(0.1)
        image_count += 1
        filename = os.path.join(images_dir, f"{image_count}.jpg")
        capture_image(filename)
        print("Petri Dish 1: Moving Motor 2 forward 400 steps...")
        move_motor(700, MOTOR2_STEP, MOTOR2_DIR, motor_id="motor2")
        for _ in range(6):
            time.sleep(0.1)
            image_count += 1
            filename = os.path.join(images_dir, f"{image_count}.jpg")
            capture_image(filename)
            move_motor(-420, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
            time.sleep(0.1)
        image_count += 1
        filename = os.path.join(images_dir, f"{image_count}.jpg")
        capture_image(filename)
        print("Petri Dish 1: Moving Motor 2 forward 400 steps...")
        if cycle < 1:
            move_motor(700, MOTOR2_STEP, MOTOR2_DIR, motor_id="motor2")  # Note: This call uses MOTOR1 if intended?
    combine_images(images_dir)
    print("Pipeline completed for Petri Dish 1.")
    print("Restoring motors to home positions...")
    if motor1_steps != 0:
        move_motor(-motor1_steps, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
    if motor2_steps != 0:
        move_motor(-motor2_steps, MOTOR2_STEP, MOTOR2_DIR, motor_id="motor2")


def run_pipeline_petri2():
    global motor1_steps
    # --- Before pipeline: Restore Motor 1 if offset ---
    if motor1_steps > 0:
        print("Restoring Motor 1 to home before Petri Dish 2 pipeline...")
        #move_motor(-6500, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
        for i in range(20):
            move_motor(-260, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
        
    session_dir = ensure_session_dir()
    dish_folder = next_petri_folder_name()
    images_dir = os.path.join(os.getcwd(), session_dir, dish_folder)
    os.makedirs(images_dir, exist_ok=True)
    
    image_count = 0
    def capture_image(filename):
        with camera_lock:
            for _ in range(5):
                video_capture.grab()
                time.sleep(0.01)
            ret, frame = video_capture.read()
        if ret:
            cv2.imwrite(filename, frame)
            print("Image saved as", filename)
        else:
            print("Failed to capture frame")
    
    print("Petri Dish 2: Moving Motor 2 forward 1 step...")
    move_motor(1, MOTOR2_STEP, MOTOR2_DIR, motor_id="motor2")
    print("Petri Dish 2: Moving Motor 1 backward 2600 steps...")
    move_motor(-3000, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
    for cycle in range(2):
        time.sleep(0.1)
        for _ in range(6):
            image_count += 1
            filename = os.path.join(images_dir, f"{image_count}.jpg")
            capture_image(filename)
            move_motor(420, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
            time.sleep(0.1)
        image_count += 1
        filename = os.path.join(images_dir, f"{image_count}.jpg")
        capture_image(filename)
        print("Petri Dish 2: Moving Motor 2 forward 400 steps...")
        move_motor(700, MOTOR2_STEP, MOTOR2_DIR, motor_id="motor2")
        for _ in range(6):
            time.sleep(0.1)
            image_count += 1
            filename = os.path.join(images_dir, f"{image_count}.jpg")
            capture_image(filename)
            move_motor(-420, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
            time.sleep(0.1)
        image_count += 1
        filename = os.path.join(images_dir, f"{image_count}.jpg")
        capture_image(filename)
        print("Petri Dish 2: Moving Motor 2 forward 400 steps...")
        if cycle < 1:
            move_motor(700, MOTOR2_STEP, MOTOR2_DIR, motor_id="motor2")
    combine_images(images_dir)
    print("Pipeline completed for Petri Dish 2.")
    print("Restoring motors to home positions...")
    if motor1_steps != 0:
        move_motor(-motor1_steps, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
    if motor2_steps != 0:
        move_motor(-motor2_steps, MOTOR2_STEP, MOTOR2_DIR, motor_id="motor2")


def run_pipeline_petri3():
    global motor1_steps
    # --- Before pipeline: Restore Motor 1 if offset ---
    if motor1_steps > 0:
        print("Restoring Motor 1 to home before Petri Dish 3 pipeline...")
        #move_motor(-6500, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
        for i in range(20):
            move_motor(-260, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
        
    session_dir = ensure_session_dir()
    dish_folder = next_petri_folder_name()
    images_dir = os.path.join(os.getcwd(), session_dir, dish_folder)
    os.makedirs(images_dir, exist_ok=True)
    
    image_count = 0
    def capture_image(filename):
        with camera_lock:
            for _ in range(5):
                video_capture.grab()
                time.sleep(0.01)
            ret, frame = video_capture.read()
        if ret:
            cv2.imwrite(filename, frame)
            print("Image saved as", filename)
        else:
            print("Failed to capture frame")
    
    print("Petri Dish 3: Moving Motor 2 forward 2600 steps...")
    move_motor(2950, MOTOR2_STEP, MOTOR2_DIR, motor_id="motor2")
    for cycle in range(2):
        time.sleep(0.1)
        for _ in range(6):
            image_count += 1
            filename = os.path.join(images_dir, f"{image_count}.jpg")
            capture_image(filename)
            move_motor(420, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
            time.sleep(0.1)
        image_count += 1
        filename = os.path.join(images_dir, f"{image_count}.jpg")
        capture_image(filename)
        print("Petri Dish 3: Moving Motor 2 forward 400 steps...")
        move_motor(700, MOTOR2_STEP, MOTOR2_DIR, motor_id="motor2")
        for _ in range(6):
            time.sleep(0.1)
            image_count += 1
            filename = os.path.join(images_dir, f"{image_count}.jpg")
            capture_image(filename)
            move_motor(-420, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
            time.sleep(0.1)
        image_count += 1
        filename = os.path.join(images_dir, f"{image_count}.jpg")
        capture_image(filename)
        print("Petri Dish 3: Moving Motor 2 forward 400 steps...")
        if cycle < 1:
            move_motor(700, MOTOR2_STEP, MOTOR2_DIR, motor_id="motor2")
    combine_images(images_dir)
    print("Pipeline completed for Petri Dish 3.")
    print("Restoring motors to home positions...")
    if motor1_steps != 0:
        move_motor(-motor1_steps, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
    if motor2_steps != 0:
        move_motor(-motor2_steps, MOTOR2_STEP, MOTOR2_DIR, motor_id="motor2")


def run_pipeline_petri4():
    global motor1_steps
    # --- Before pipeline: Restore Motor 1 if offset ---
    if motor1_steps > 0:
        print("Restoring Motor 1 to home before Petri Dish 4 pipeline...")
        #move_motor(-6500, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
        for i in range(20):
            move_motor(-260, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
        
    session_dir = ensure_session_dir()
    dish_folder = next_petri_folder_name()
    images_dir = os.path.join(os.getcwd(), session_dir, dish_folder)
    os.makedirs(images_dir, exist_ok=True)
    
    image_count = 0
    def capture_image(filename):
        with camera_lock:
            for _ in range(5):
                video_capture.grab()
                time.sleep(0.01)
            ret, frame = video_capture.read()
        if ret:
            cv2.imwrite(filename, frame)
            print("Image saved as", filename)
        else:
            print("Failed to capture frame")
    
    print("Petri Dish 4: Moving Motor 2 forward 2600 steps...")
    move_motor(2950, MOTOR2_STEP, MOTOR2_DIR, motor_id="motor2")
    print("Petri Dish 4: Moving Motor 1 backward 2600 steps...")
    move_motor(-3000, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
    for cycle in range(2):
        time.sleep(0.1)
        for _ in range(6):
            image_count += 1
            filename = os.path.join(images_dir, f"{image_count}.jpg")
            capture_image(filename)
            move_motor(420, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
            time.sleep(0.1)
        image_count += 1
        filename = os.path.join(images_dir, f"{image_count}.jpg")
        capture_image(filename)
        print("Petri Dish 4: Moving Motor 2 forward 400 steps...")
        move_motor(700, MOTOR2_STEP, MOTOR2_DIR, motor_id="motor2")
        for _ in range(6):
            time.sleep(0.1)
            image_count += 1
            filename = os.path.join(images_dir, f"{image_count}.jpg")
            capture_image(filename)
            move_motor(-420, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
            time.sleep(0.1)
        image_count += 1
        filename = os.path.join(images_dir, f"{image_count}.jpg")
        capture_image(filename)
        print("Petri Dish 4: Moving Motor 2 forward 400 steps...")
        if cycle < 1:
            move_motor(700, MOTOR2_STEP, MOTOR2_DIR, motor_id="motor2")
    combine_images(images_dir)
    print("Pipeline completed for Petri Dish 4.")
    print("Restoring motors to home positions...")
    if motor1_steps != 0:
        move_motor(-motor1_steps, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
    if motor2_steps != 0:
        move_motor(-motor2_steps, MOTOR2_STEP, MOTOR2_DIR, motor_id="motor2")


# ----- Sequential Thread Functions -----
def run_petri1_thread():
    def sequential():
        run_pipeline_petri1()
        print("Returning Motor 1 to offset position (-6500 steps) after pipeline...")
        #move_motor(6500, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
        for i in range(20):
            move_motor(260, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
    threading.Thread(target=sequential).start()

def run_petri2_thread():
    def sequential():
        run_pipeline_petri1()
        run_pipeline_petri2()
        print("Returning Motor 1 to offset position (-6500 steps) after pipeline...")
        #move_motor(6500, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
        for i in range(20):
            move_motor(260, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
    threading.Thread(target=sequential).start()

def run_petri3_thread():
    def sequential():
        run_pipeline_petri1()
        run_pipeline_petri2()
        run_pipeline_petri3()
        print("Returning Motor 1 to offset position (-6500 steps) after pipeline...")
        #move_motor(6500, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
        for i in range(20):
            move_motor(260, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
    threading.Thread(target=sequential).start()

def run_petri4_thread():
    def sequential():
        run_pipeline_petri1()
        run_pipeline_petri2()
        run_pipeline_petri3()
        run_pipeline_petri4()
        print("Returning Motor 1 to offset position (-6500 steps) after pipeline...")
        #move_motor(6500, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
        for i in range(20):
            move_motor(260, MOTOR1_STEP, MOTOR1_DIR, motor_id="motor1")
    threading.Thread(target=sequential).start()

# ============================================
# Part 2: GUI – Modern In‑Line Button Design with Camera Preview
# ============================================
# Color scheme
BG_COLOR = "#2E3440"         # Dark blue-gray
BUTTON_COLOR = "#5E81AC"     # Soft blue
BUTTON_HOVER_COLOR = "#81A1C1"  # Lighter blue
TEXT_COLOR = "#ECEFF4"       # Light gray

# Define dimensions:
main_width = 940
main_height = 1080
left_img_width = 480
right_img_width = 500

# Overall window dimensions: left image + main area + right image
overall_width = left_img_width + main_width + right_img_width
overall_height = main_height

# Create main window
root = tk.Tk()
# Hide the native title bar
root.overrideredirect(True)

# --- Custom Title Bar (using pack) ---
title_bar = tk.Frame(root, bg="white", relief="raised", bd=2, height=50)
title_bar.pack(side="top", fill="x")

# Optional: Load an icon (adjust the path as needed)
try:
    img = Image.open("/home/ncai/Desktop/APP/icon.png").resize((40, 40))
    icon = ImageTk.PhotoImage(img)
except Exception as e:
    print("Error loading icon:", e)
    icon = None
    

# Title label with big text and optional icon
title_label = tk.Label(title_bar, text=" Imaging", fg="black", bg="white",
                        font=("Arial", 20, "bold"), image=icon, compound="left")
title_label.image = icon  # Keep a reference to prevent garbage collection
title_label.pack(side="left", padx=10, pady=5)

# Close button for the custom title bar
#close_btn = tk.Button(title_bar, text="X", bg="red", fg="white", font=("Arial", 14, "bold"),
#                      command=lambda: (GPIO.cleanup(), video_capture.release(), root.destroy()),
#                      relief="flat")
#close_btn.pack(side="right", padx=10, pady=5)


# --- Create a content frame for the rest of the GUI ---
content_frame = tk.Frame(root)
content_frame.pack(side="top", fill="both", expand=True)

# Now use grid inside the content_frame
global_container = tk.Frame(content_frame, bg=BG_COLOR)
global_container.grid(row=0, column=0, sticky="nsew")

# Set window dimensions (applied to the root)
root.geometry(f"{overall_width}x{overall_height}")
root.configure(bg=BG_COLOR)
root.resizable(False, False)

# Configure grid for the content frame
content_frame.columnconfigure(0, weight=1)
content_frame.rowconfigure(0, weight=1)


# Create a global container that holds the left image, main area, and right image.
global_container.columnconfigure(0, weight=0)  # Left image
global_container.columnconfigure(1, weight=0)  # Main area
global_container.columnconfigure(2, weight=0)  # Right image
global_container.rowconfigure(0, weight=1)

# --- Left Image ---
try:
    left_image = Image.open("/home/ncai/Desktop/APP/image1.jpg")
except Exception as e:
    print("Error loading left image:", e)
    left_image = Image.new("RGB", (left_img_width, main_height), color="gray")
left_image = left_image.resize((left_img_width, main_height), Image.LANCZOS)
left_photo = ImageTk.PhotoImage(left_image)
left_label = tk.Label(global_container, image=left_photo, bg=BG_COLOR)
left_label.image = left_photo  # Keep a reference!
left_label.grid(row=0, column=0, padx=10, pady=5, sticky="nsew")

# --- Main Area ---
main_area = tk.Frame(global_container, width=main_width, height=main_height, bg=BG_COLOR)
main_area.grid(row=0, column=1, padx=30, pady=5, sticky="nsew")
main_area.grid_propagate(False)  # Prevent resizing based on its content

# Configure grid within the main area: row 0 for the camera preview, row 1 for the buttons
main_area.rowconfigure(0, weight=30)  # Camera preview area gets more space
main_area.rowconfigure(1, weight=0)  # Button area
main_area.columnconfigure(0, weight=1)

# Create a top frame for the camera preview in the main area
camera_frame = tk.Frame(main_area, bg=BG_COLOR)
camera_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
camera_label = tk.Label(camera_frame, bg=BG_COLOR)
camera_label.pack(expand=True, fill="both")

# Start updating the camera preview
root.after(0, update_camera)

# Main frame for buttons placed below the camera preview within the main area
main_frame = ttk.Frame(main_area, padding=5)
main_frame.grid(row=1, column=0, sticky="nsew")
main_frame.columnconfigure(0, weight=1)
main_frame.columnconfigure(1, weight=1)


# TTK styling for a modern look
style = ttk.Style()
style.theme_use("clam")
style.configure("TFrame", background=BG_COLOR)
style.configure("TLabel", font=("Arial", 16), background="#ffffff", padding=10)
style.configure("TButton", font=("Arial", 16, "bold"), padding=(16, 14),
                background=BUTTON_COLOR, foreground=TEXT_COLOR)
style.map("TButton",
          background=[("active", BUTTON_HOVER_COLOR), ("!active", BUTTON_COLOR)],
          foreground=[("active", TEXT_COLOR), ("!active", TEXT_COLOR)])


# Row 0: Capture 1 or 2 Petri Dishes this run
btn1 = ttk.Button(main_frame, text="Capture 1 Petri Dish", command=run_petri1_thread, style="TButton")
btn1.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
btn2 = ttk.Button(main_frame, text="Capture 2 Petri Dishes", command=run_petri2_thread, style="TButton")
btn2.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

# Row 1: Capture 3 or 4 Petri Dishes this run
btn3 = ttk.Button(main_frame, text="Capture 3 Petri Dishes", command=run_petri3_thread, style="TButton")
btn3.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
btn4 = ttk.Button(main_frame, text="Capture 4 Petri Dishes", command=run_petri4_thread, style="TButton")
btn4.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

# Row 2: Quit/Menu button spanning both columns
quit_btn = ttk.Button(
    main_frame,
    text="☰ Menu",
    command=lambda: (GPIO.cleanup(), video_capture.release(), root.destroy()),
    style="TButton"
)
quit_btn.grid(row=0, column=3, columnspan=2, padx=5, pady=5, sticky="ew")

# --- Right Image ---
try:
    right_image = Image.open("/home/ncai/Desktop/APP/image2.jpg")
except Exception as e:
    print("Error loading right image:", e)
    right_image = Image.new("RGB", (right_img_width, main_height), color="gray")
right_image = right_image.resize((right_img_width, main_height), Image.LANCZOS)
right_photo = ImageTk.PhotoImage(right_image)
right_label = tk.Label(global_container, image=right_photo, bg=BG_COLOR)
right_label.image = right_photo  # Keep a reference!
right_label.grid(row=0, column=2, padx=10, pady=5, sticky="nsew")
# ============================================
# Main Guard – Run the Imaging GUI
# ============================================
if __name__ == "__main__":
    root.mainloop()
