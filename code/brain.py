from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import os
os.chdir("/root/ooblex/")
import re
import tensorflow as tf
import numpy as np
import cv2
import binascii
import threading
from multiprocessing import Process
import time
import sys
import detect_face
import ssl
from amqpstorm import UriConnection
from amqpstorm import Message
import uuid
import logging
import datetime
import json
import math
import urllib

from model import autoencoder_A, autoencoder_B, autoencoder_A_swift
from model import encoder, decoder_A, decoder_B, decoder_A_swift, encoder_swift
from keras import backend as K
import redis

global graph, r

encoder.load_weights( "models/encoder256.h5"   )
decoder_A.load_weights( "models/decoder256_A.h5" )
decoder_B.load_weights( "models/decoder256_B.h5" )

encoder_swift.load_weights( "models/encoder256_ENCODER.h5"   )
decoder_A_swift.load_weights( "models/decoder256_A_TAYLOR.h5" )
#decoder_B_swift.load_weights( "models/decoder256_B_swift.h5" )


graph = tf.get_default_graph()

redisUrl = "rediss://admin:GSURJCGDVFWYOLYD@portal1369-16.bmix-dal-yp-cbfabb84-69f1-472d-87d7-343fd70e44c6.steve-seguin-email.composedb.com:40299"
r = redis.Redis.from_url(redisUrl)
#logging.basicConfig(level=logging.DEBUG)
def tensorThread(something):

	class NodeLookup():
		def __init__(self, label_lookup_path=None, uid_lookup_path=None):
			if not label_lookup_path:
				label_lookup_path = 'inception/imagenet_2012_challenge_label_map_proto.pbtxt'
			if not uid_lookup_path:
				uid_lookup_path = 'inception/imagenet_synset_to_human_label_map.txt'
			self.node_lookup = self.load(label_lookup_path, uid_lookup_path)

		def load(self, label_lookup_path, uid_lookup_path):
			if not tf.gfile.Exists(uid_lookup_path):
				tf.logging.fatal('File does not exist %s', uid_lookup_path)
			if not tf.gfile.Exists(label_lookup_path):
				tf.logging.fatal('File does not exist %s', label_lookup_path)
			# Loads mapping from string UID to human-readable string
			proto_as_ascii_lines = tf.gfile.GFile(uid_lookup_path).readlines()
			uid_to_human = {}
			p = re.compile(r'[n\d]*[ \S,]*')
			for line in proto_as_ascii_lines:
				parsed_items = p.findall(line)
				uid = parsed_items[0]
				human_string = parsed_items[2]
				uid_to_human[uid] = human_string
			#return uid_to_human
			# Loads mapping from string UID to integer node ID.
			node_id_to_uid = {}
			proto_as_ascii = tf.gfile.GFile(label_lookup_path).readlines()
			for line in proto_as_ascii:
				if line.startswith('	target_class:'):
					target_class = int(line.split(': ')[1])
				if line.startswith('	target_class_string:'):
					target_class_string = line.split(': ')[1]
					node_id_to_uid[target_class] = target_class_string[1:-2]
			# Loads the final mapping of integer node ID to human-readable string
			node_id_to_name = {}
			for key, val in node_id_to_uid.items():
				if val not in uid_to_human:
					tf.logging.fatal('Failed to locate: %s', val)
				name = uid_to_human[val]
				node_id_to_name[key] = name
			return node_id_to_name
			
			
	def create_graph():
		with tf.gfile.FastGFile("inception/classify_image_graph_def.pb", 'rb') as f:
			graph_def = tf.GraphDef()
			graph_def.ParseFromString(f.read())
			_ = tf.import_graph_def(graph_def, name='')


	def url_to_image(url):
		try:
			resp = urllib.request.urlopen(url)
		except:
			print("Invalid Image")
			return False
		image = np.asarray(bytearray(resp.read()), dtype="uint8")
		image = cv2.imdecode(image, cv2.IMREAD_COLOR)
		image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
		return image

	create_graph()
	minsize = 200 # minimum size of face
	threshold = [ 0.5, 0.6, 0.7 ]	# three steps's threshold
	factor = 0.709 # scale factor


	def sendMessage(msg,token):
		global mainchannel_out
		data = {}
		data['msg'] = msg
		data['key'] = token
		msg = json.dumps(data)
		#print("sending message:",msg)
		msg = Message.create(mainChannel_out, msg)
		msg.publish('broadcast-all')

	childChannel = mainConnection.channel()
	childChannel.queue.declare("tf-task", arguments={'x-message-ttl':1000})
	childChannel.basic.qos( 1 , global_ = True )

	def processTask(msg0):
		childChannel.stop_consuming()
		msg = msg0.body
		msg = json.loads(msg)
		if (msg['task']=="ObjectOn"):
			#img = url_to_image(msg['url'])

			image = np.asarray(r.get(msg['redisID']), dtype="uint8")
			image = cv2.imdecode(image, cv2.IMREAD_COLOR)
			image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
			
			if type(img) == type(None):
				print("no image on redis")
				return

			if type(img) == type(False):
				print("couldnt process")
				return
			objectDetection(img, msg['streamKey'])
		elif (msg['task']=="TrumpOn"):
			try:	
				image = np.asarray(bytearray(r.get(msg['redisID'])), dtype="uint8")
			except:
				return
			image = cv2.imdecode(image, cv2.IMREAD_COLOR)
			
			if type(image) == type(False):
				print("couldnt process 2")
				return
			faceDetection(image, msg['streamKey'], msg['redisID'], "trump")
		elif (msg['task']=="FaceOn"):
			try:	
				image = np.asarray(bytearray(r.get(msg['redisID'])), dtype="uint8")
			except:
				return
			image = cv2.imdecode(image, cv2.IMREAD_COLOR)
			
			if type(image) == type(False):
				print("couldnt process 2")
				return
			faceDetection(image, msg['streamKey'], msg['redisID'],"avg")
		elif (msg['task']=="SwiftOn"):
			try:
				image = np.asarray(bytearray(r.get(msg['redisID'])), dtype="uint8")
			except:
				return
			image = cv2.imdecode(image, cv2.IMREAD_COLOR)
		
			if type(image) == type(False):
				print("couldnt process 2")
				return
			faceDetection(image, msg['streamKey'], msg['redisID'], "swift")
		elif (msg['task']=="saveImage"):
			sendMessage(msg['redisID'], msg['streamKey'])
		else:
			print("unknown task: ",msg['task'])
		msg0.ack()
		return
			
################
	#print("loading object detector")
	#sess_thing = tf.Session()
	#softmax_tensor = sess_thing.graph.get_tensor_by_name('softmax:0')
################
	print("loading face detector")
	sess_face = tf.Session()
	pnet, rnet, onet = detect_face.create_mtcnn(sess_face, None)
	###
	W,H = 256,256
	alpha = np.zeros((H,W), np.uint8)
	cv2.ellipse(alpha, (int(W/2), int(H/2)), (int(W/2-3), int(H/2-3)), 0.0, 0.0, 360.0, (255, 255, 255), -1, cv2.LINE_AA);
	alpha = cv2.GaussianBlur(alpha, (21,21),14 )
	alpha = cv2.cvtColor(alpha, cv2.COLOR_GRAY2BGR)/255.0
##############
	#print("loading smile detector")
	#sess_smile = tf.Session()
	#with tf.gfile.FastGFile("emotions.pb", 'rb') as f:
	#	graph_def = tf.GraphDef()
	#	graph_def.ParseFromString(f.read())
	#	_ = tf.import_graph_def(graph_def, name='')
	#frame_window = 10
	#emotion_offsets = (20, 40)
	#smile_input_layer = sess_smile.graph.get_tensor_by_name('output_node0:0')
###########################
	def faceDetection(img, token, rid, dectype="trump"):
		global graph, r
		img2=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
		bounding_boxes, points = detect_face.detect_face(img2, minsize, pnet, rnet, onet, threshold, factor)
		with graph.as_default():
			for box in bounding_boxes:
				try:
					if box[3]-box[1] < box[2]-box[0]:
						delta = int((box[2]-box[0])-(box[3]-box[1]) - (box[2]-box[0])*0.2)/2
						box[3]+=delta
						box[1]-=delta
						
						box[2]-=int((box[2]-box[0])*0.1)
						box[0]+=int((box[2]-box[0])*0.1)
					else:
						delta = int((box[3]-box[1])-(box[2]-box[0]) - (box[3]-box[1])*0.2)/2
						box[2]+=delta
						box[0]-=delta
						
						box[3]-=int((box[3]-box[1])*0.1)
						box[1]+=int((box[3]-box[1])*0.1)

					
					image = img[int(box[1]):int(box[3]+1),int(box[0]):int(box[2]+1),:]

					ss = image.shape
					if (ss[0]*ss[1])==0:
						continue
					IMG_COL = 256
					IMG_ROW = 256
					border_v = 0
					border_h = 0
				
					if (IMG_COL/IMG_ROW) >= (image.shape[0]/image.shape[1]):
						border_v = int((((IMG_COL/IMG_ROW)*image.shape[1])-image.shape[0])/2)
						image = cv2.copyMakeBorder(image, border_v, border_v, 0, 0, cv2.BORDER_REPLICATE, 0)
					else:
						border_h = int((((IMG_ROW/IMG_COL)*image.shape[0])-image.shape[1])/2)
						image = cv2.copyMakeBorder(image, 0, 0, border_h, border_h, cv2.BORDER_REPLICATE, 0) 
					
				except Exception as e:
					print(e)
					continue

				try:
					
					ss = image.shape
					#print(ss)
					image = cv2.resize(image, (IMG_ROW, IMG_COL))/255.0
					#cv2.normalize(image, image, 0, 1.0, norm_type=cv2.NORM_MINMAX)
					test = np.empty( (1,) + image.shape, image.dtype )
					test[0] = image
					if (dectype=="trump"):
						figure = autoencoder_A.predict( test )
					elif (dectype=="swift"):
						figure = autoencoder_A_swift.predict( test )
					else:
						figure = autoencoder_B.predict( test )
					a1     = cv2.resize(alpha, (ss[1],ss[0]))
					figure = cv2.resize(figure[0,:,:,:], (ss[1],ss[0]))  #[border_h:-border_h,:,:]
					figure = cv2.filter2D(figure, -1, np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]]))
					figure  = np.clip( figure*255.0 , 0, 255 ).astype('uint8')
					img[int(box[1]):int(box[1])+ss[0],int(box[0]):int(box[0]+ss[1]),:] = cv2.convertScaleAbs(img[int(box[1]):int(box[1])+ss[0],int(box[0]):int(box[0]+ss[1]),:]*(1-a1) + figure*a1)
				except ValueError as e:
					print(e)
		
		jpg = cv2.imencode(".jpg", img)[1].tostring()
		rid = rid+":face"
		r.set(rid, jpg, ex=30)
		r.publish(token+"face", rid)
		#print(token,rid)
		return
#			predictions = sess_smile.run(smile_input_layer, {'input_1:0': face})
#			predictions = np.squeeze(predictions)
#			emote = np.where(predictions==np.amax(predictions))[0]
#			if (emote==3):
				#print("happy score: "+str(predictions[3]))
#				if (predictions[3]>0.5):
#					sendMessage("Smile Detected!", token)
#					filename = uuid.uuid4().hex+".jpg"
#					cv2.imwrite("/var/www/html/images/"+filename,cv2.cvtColor(img,cv2.COLOR_RGB2BGR))
					#print("https://api.ooblex.com/images/"+filename)
#					sendMessage("https://api.ooblex.com/images/"+filename, token)

				#print(predictions)
	def objectDetection(img, token):
		predictions = sess_thing.run(softmax_tensor, {'DecodeJpeg:0': img})
		predictions = np.squeeze(predictions)
		return
		node_lookup = NodeLookup()
		top_k = predictions.argsort()[-1:][::-1]  ## top 3 predictions
		for node_id in top_k:
			human_string = str(node_lookup.node_lookup[str(node_id)])
			score = predictions[node_id]
			print('%s (score = %.5f)' % (human_string, score))
			output = '%s (score = %.5f)' % (human_string, score)
			sendMessage("Object Detected: "+output, token)







	while True:
		result = childChannel.basic.get("tf-task", no_ack=False)
		if not result:
			childChannel.basic.consume(processTask, "tf-task", no_ack=False)
			childChannel.start_consuming()
			continue
		processTask(result)

#	childChannel = mainConnection.channel()
#	childChannel.queue.declare("tf-task", arguments={'x-message-ttl':1000})
#	childChannel.basic.consume(processTask, "tf-task", no_ack=False)
#	childChannel.basic.qos( 1 , global_ = True )
#	childChannel.start_consuming()

while True:
	try:
		mainConnection = UriConnection("amqps://admin:QYGTGMPLVLFYOPRH@portal-ssl494-22.bmix-dal-yp-42bf8654-c98e-426b-b8e4-a9d19926bfde.steve-seguin-email.composedb.com:39186/bmix-dal-yp-42bf8654-c98e-426b-b8e4-a9d19926bfde")
		break
	except:
		print("Couldn't connect to rabbitMQ server. Retrying")
		time.sleep(3)
		continue

global mainchannel_out
mainChannel_out = mainConnection.channel()
mainChannel_in = mainConnection.channel()

def processMessage(message):
	message.ack()
	#print(message.body)
	tensorThread(message.body) ## 

#p = Process(target=tensorThread, args=(None,))
p = threading.Thread(target=tensorThread, args=(None,))
p.start()
p = threading.Thread(target=tensorThread, args=(None,))
p.start()
p = threading.Thread(target=tensorThread, args=(None,))
p.start()
p = threading.Thread(target=tensorThread, args=(None,))
p.start()
p = threading.Thread(target=tensorThread, args=(None,))
p.start()
p = threading.Thread(target=tensorThread, args=(None,))
p.start()
p = threading.Thread(target=tensorThread, args=(None,))
p.start()
p = threading.Thread(target=tensorThread, args=(None,))
p.start()
p = threading.Thread(target=tensorThread, args=(None,))
p.start()
p = threading.Thread(target=tensorThread, args=(None,))
p.start()
p = threading.Thread(target=tensorThread, args=(None,))
p.start()


print("TensorFlow Server started")
mainChannel_in.queue.declare("tf-controller", arguments={'x-message-ttl':3600000}) ### Spin up more threads if needed; this should be un-used I'd suspect
mainChannel_in.basic.consume(processMessage, 'tf-controller', no_ack=False)
mainChannel_in.basic.qos( 1 , global_ = True )
mainChannel_in.start_consuming()
