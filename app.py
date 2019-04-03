# The webserver module
from flask import Flask, render_template, redirect, url_for, session, request, url_for, jsonify
from flask_socketio import SocketIO, emit

# OpenCV and other Face Recogition modules
import cv2
import imutils
import face_recognition
from pickle import loads

# Other support modules
import os
import zipfile
from base64 import b64encode
from configparser import ConfigParser
from werkzeug.utils import secure_filename

# Custom modules
from modules.base64_2_image import data_uri_to_cv2_img

# Parsing config
config = ConfigParser()
config.read('config.ini')
greet_name = 'UNKNOWN'

args={}
args["dataset"]=config.get('arg', 'dataset')
args["encodings"]=config.get('arg', 'encodings')
args["detection-method"]=config.get('arg', 'detection-method')

# Loading data
data = loads(open(args["encodings"], "rb").read())

# Basic app setup
app = Flask(__name__, static_url_path='', static_folder='web/static', template_folder='web/templates')
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, ping_interval=2000, ping_timeout=120000)

# Initializing config for file uploader
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'dataset')
ALLOWED_EXTENSIONS = set(['zip'])

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Defining routes
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload')
def upload():
    return render_template('uploader.html')


@app.route('/upload-file', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        # check if the post request has the file part
        if 'uploads[]' not in request.files:
            return jsonify(status="ERROR", message="No file in request.files")
        
        file = request.files['uploads[]']
        
        # if user does not select file, browser also
        # submit a empty part without filename
        if file.filename == '':
            return jsonify(status="ERROR", message="No file selected")
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            zip_ref = zipfile.ZipFile(os.path.join(UPLOAD_FOLDER, filename), 'r')
            zip_ref.extractall(UPLOAD_FOLDER)
            zip_ref.close()
            return jsonify(status="SUCCESS")
    
    return jsonify(status="ERROR", message="Post method not used")

# Socket operations
@socketio.on('connect')
def onconnect():
    print('Got a connection')

@socketio.on('disconnect')
def ondisconnect():
    print('Client disconnected')
    cv2.destroyAllWindows()

@socketio.on('stream')
def onimage(img):
    frame = data_uri_to_cv2_img(img)
    frame = imutils.resize(frame, width=400)
    
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    r = frame.shape[1] / float(rgb.shape[1])

    # detect the (x, y)-coordinates of the bounding boxes
	# corresponding to each face in the input frame, then compute
	# the facial embeddings for each face
    boxes = face_recognition.face_locations(rgb, model=args["detection-method"])
    encodings = face_recognition.face_encodings(rgb, boxes)

    names = []
    name = "Unknown"

    # loop over the facial embeddings
    for encoding in encodings:
        # attempt to match each face in the input image to our known encodings
        matches = face_recognition.compare_faces(data["encodings"], encoding)

        # check to see if we have found a match
        if True in matches:
            # find the indexes of all matched faces then initialize a
            # dictionary to count the total number of times each face was matched
            matchedIdxs = [i for (i, b) in enumerate(matches) if b]
            counts = {}

            # loop over the matched indexes and maintain a count for each recognized face face
            for i in matchedIdxs:
                name = data["names"][i]
                counts[name] = counts.get(name, 0) + 1

            # determine the recognized face with the largest number of votes 
            # (note: in the event of an unlikely tie Python will select first entry in the dictionary)
            name = max(counts, key=counts.get)

        # update the list of names
        names.append(name)

    # loop over the recognized faces
    for ((top, right, bottom, left), name) in zip(boxes, names):
        
        # rescale the face coordinates
        top = int(top * r)
        right = int(right * r)
        bottom = int(bottom * r)
        left = int(left * r)

        # draw the predicted face name on the image
        cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
        y = top - 15 if top - 15 > 15 else top + 15
        cv2.putText(frame, name, (left, y), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)

    # Detect new person in stream and send its name
    if name != greet_name and name!="Unknown":
        emit('person_name', name)
        name = greet_name

    # Encoding and send data back to the client
    retval, buffer = cv2.imencode('.jpg', frame)
    emit('media', b64encode(buffer))


# Starting the program
if __name__ == '__main__':
    socketio.run(app)