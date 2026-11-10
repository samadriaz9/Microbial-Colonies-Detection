"""
Simple app to upload an image via a web form 
and view the inference results on the image in the browser.
"""
import argparse
import io
import math
import os
import numpy as np
from PIL import Image
import datetime
import cv2
import torch
from flask import Flask, render_template, request, redirect, url_for, flash

from flask_paginate import Pagination


app = Flask(__name__)

DATETIME_FORMAT = "%Y-%m-%d_%H-%M-%S-%f"

@app.route("/", methods=["GET", "POST"])
def predict():
    if request.method == "POST":
        files = request.files.getlist("file")
        img_savenames = []

        all_results = []  # To store results for all images
        total_detected_objects = 0

        for file in files:
            if file.filename == '':
                continue

            img_bytes = file.read()
            img = Image.open(io.BytesIO(img_bytes))
            print(type(img))
            print('img type printed')
            results = model([img])
            result_txt = str(results)
            r_t = result_txt.split('\n')[0].split(':')[1].lstrip().split()[1:]
            r_t_final = ''
            for i in r_t:
                r_t_final += " " + i
            print(results)
            results.render()
            now_time = datetime.datetime.now().strftime(DATETIME_FORMAT)
            img_savename = f"static/{now_time}.png"
            # Convert the result image to a writable NumPy array
            result_img = np.asarray(results.ims[0]).copy()

            # Add text to the writable image
            cv2.putText(
                result_img,
                text=r_t_final,
                org=(10, 40),
                fontFace=cv2.FONT_HERSHEY_DUPLEX,
                fontScale=1.0,
                color=(125, 246, 55),
                thickness=2
            )

# # Update the result image back to the results.ims format
# results.ims[0] = result_img

#             all_results.append((Image.fromarray(results.ims[0]), len(r_t)))
#             total_detected_objects += len(r_t)

#             Image.fromarray(results.ims[0]).save(img_savename)
#             img_savenames.append(img_savename)

        # Combine images into an 8x5 pattern
        rows = 7
        cols = 4
        combined_width = all_results[0][0].width * cols
        combined_height = all_results[0][0].height * rows
        combined_img = Image.new('RGB', (combined_width, combined_height), (255, 255, 255))

        row_index = 0
        col_index = 0

        for img, detected_objects in all_results:
            combined_img.paste(img, (col_index * img.width, row_index * img.height))
            cv2.putText(
                np.array(combined_img),
                text=f"Detected Objects: {detected_objects}",
                org=(col_index * img.width + 10, row_index * img.height + 40),
                fontFace=cv2.FONT_HERSHEY_DUPLEX,
                fontScale=1.0,
                color=(125, 246, 55),
                thickness=2)

            col_index += 1
            if col_index >= cols:
                col_index = 0
                row_index += 1

        # Save the original combined image
        combined_img.save("static/combined_original.png")
        # return redirect("/results")

        return render_template("results.html", img_path_original="static/combined_original.png", heading="Detected E. Coli Images", total_detected_objects=total_detected_objects)


    return render_template("index.html")


@app.route("/results")
def show_results():
    # Your results rendering code here
    return render_template("results.html")

def get_page_args(page_parameter='page', per_page_parameter='per_page'):
    page = request.args.get(page_parameter, 1, type=int)
    per_page = request.args.get(per_page_parameter, 9, type=int)
    return page, per_page, (page - 1) * per_page

@app.route('/images', methods=['GET', 'POST'])
def images():
    # Get the list of files from the static folder.
    static_folder = app.static_folder
    files = os.listdir(os.path.join(app.root_path, static_folder))

    # Calculate the current page, the number of images to display per page,
    # and the starting index of the images to display on the current page.
    page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')
    print("page, per_page, offset", page, ", ", per_page, ", ", offset)
    # per_page = 9
    offset = (page - 1) * per_page

    # Determine the current page number.
    page_num = page # Pages are 0-indexed, so add 1.
    prev_num = page -1
    next_num = page + 1
    
    # Get the files to display on the current page.
    files_to_show = files[offset:offset+per_page]

    # Calculate the total number of pages.
    total_pages = int(math.ceil(len(files) / float(per_page)))

    
    # Create a pagination object.
    pagination = Pagination(page=page, per_page=per_page, total=len(files), css_framework='bootstrap4')
    

    # Render the template with the pagination object and the file list.
    return render_template('images.html', files=files_to_show, pagination=pagination, total_pages=total_pages, current_page=page, per_page=per_page, page_num=page_num)


@app.route('/delete', methods=['POST'])
def delete():
    filename = request.form['filename']
    print(f"Delete button called on image {filename}")
    full_path = os.path.join(app.static_folder, filename)
    if os.path.exists(full_path):
        os.remove(full_path)
        print(f"image {full_path} deleted.")
    return redirect(url_for('images'))

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        message = request.form['message']
        # Process the form data (e.g., send an email, save to a database, etc.)
        flash('Thank you for your message!', 'success')
        return redirect(url_for('contact'))
    return render_template('contact.html')

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flask app exposing yolov5 models")
    parser.add_argument("--port", default=5001, type=int, help="port number")
    args = parser.parse_args()

    model = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True)  # force_reload = recache latest code
    model.eval()
    # model.names[0] = 'proteus'
    model.conf = 0.60
    app.run(host="0.0.0.0", port=args.port)  # debug=True causes Restarting with stat