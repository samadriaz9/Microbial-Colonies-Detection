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
from flask import Flask, render_template, request, redirect, url_for
from flask_paginate import Pagination
app = Flask(__name__)
DATETIME_FORMAT = "%Y-%m-%d_%H-%M-%S-%f"
@app.route("/", methods=["GET", "POST"])
def predict():
    if request.method == "POST":
        files_org_pattern = request.files.getlist("file")
        # pattern = [4,3,2,1,0, 5,6,7,8,9, 14,13,12,11,10,15,16,17,18,19, 24,23,22,21,20, 25,26,27,28,29, 34,33,32,31,30, 35,36,37,38,39]
        # pattern = [40,39,38,37,36,31,32,33,34,35,30,29,28,27,26,21,22,23,24,25,20,19,18,17,16,11,12,13,14,15,10,9,8,7,6,1,2,3,4,5]
        # pattern = [39, 38, 37, 36, 35, 30, 31, 32, 33, 34, 29, 28, 27, 26, 25, 20, 21, 22, 23, 24, 19, 18, 17, 16, 15, 10, 11, 12, 13, 14, 9, 8, 7, 6, 5, 0, 1, 2, 3, 4]
        pattern = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]
        files = [files_org_pattern[i] for i in pattern]
        print(files)
        img_savenames = []
        # print(files)
        all_results = []  # To store results for all images
        total_detected_objects = 0

        for file in files:
            if file.filename == '':
                continue

            img_bytes = file.read()
            img = Image.open(io.BytesIO(img_bytes))
            results = model([img])
            result_txt = str(results)
            r_t = result_txt.split('\n')[0].split(':')[1].lstrip().split()[1:]
            # r_t_final = ''
            # for i in r_t:
                # r_t_final += " " + i

            results.render()
            now_time = datetime.datetime.now().strftime(DATETIME_FORMAT)
            img_savename = f"static/{now_time}.png"
            # results.ims[0] = cv2.putText(
            #     results.ims[0],
            #     text=r_t_final,
            #     org=(10, 40),
            #     fontFace=cv2.FONT_HERSHEY_DUPLEX,
            #     fontScale=1.0,
            #     color=(125, 246, 55),
            #     thickness=2)
            # all_results.append(Image.fromarray(results.ims[0]))
            all_results.append((Image.fromarray(results.ims[0]), len(r_t)))
            # total_detected_objects += len(r_t)

            # Image.fromarray(results.ims[0]).save(img_savename)
            img_savenames.append(img_savename)

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
            # cv2.putText(
            #     np.array(combined_img),
            #     text=f"Detected Objects: {detected_objects}",
            #     org=(col_index * img.width + 10, row_index * img.height + 40),
            #     fontFace=cv2.FONT_HERSHEY_DUPLEX,
            #     fontScale=1.0,
            #     color=(125, 246, 55),
            #     thickness=2)

            col_index += 1
            if col_index >= cols:
                col_index = 0
                row_index += 1
        img_savename = 'static/combined_original.png'
        # Save the original combined image
        combined_img.save(img_savename)
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



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flask app exposing yolov5 models")
    # parser.add_argument("--port", default=443, type=int, help="port number")
    args = parser.parse_args()

    model = torch.hub.load('ultralytics/yolov5', 'yolov5s', pretrained=True)  # force_reload = recache latest code
    model.eval()
    # model.names[0] = 'proteus'
    model.conf = 0.20
    app.run(host="0.0.0.0")  # debug=True causes Restarting with state