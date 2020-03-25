from __future__ import print_function

import base64
import json
import boto3
import time
import sys
import cv2
from boto3.dynamodb.conditions import Key
from random import randint

sys.path.insert(1, '/opt')


def lambda_handler(event, context):
    print("event =======")
    print(event)
    streamName = "LiveRekognitionVideoAnalysisBlog"
    streamArn = "arn:aws:kinesisvideo:us-west-2:655546244197:stream/LiveRekognitionVideoAnalysisBlog/1572919264579"
    personDetected = False
    for record in event['Records']:
        # Kinesis data is base64 encoded so decode here
        if personDetected is True:
            break
        payload = base64.b64decode(record['kinesis']['data'])
        result = json.loads(payload.decode('utf-8'))
        print(result['InputInformation'])
        if len(result['FaceSearchResponse']) > 0:
            personDetected = True
            print("FaceSearchResponse not empty =" + json.dumps(result['FaceSearchResponse']))
        else:
            continue
        faceResponse = result['FaceSearchResponse']
        frag_id = result['InputInformation']['KinesisVideo']['FragmentNumber']
        print("frag_id =", frag_id)

        kvs = boto3.client("kinesisvideo")
        # Grab the endpoint from GetDataEndpoint
        endpoint = kvs.get_data_endpoint(
            APIName="GET_HLS_STREAMING_SESSION_URL",
            StreamName=streamName
        )['DataEndpoint']

        # # Grab the HLS Stream URL from the endpoint
        kvam = boto3.client("kinesis-video-archived-media", endpoint_url=endpoint)
        url = kvam.get_hls_streaming_session_url(
            StreamName=streamName,
            PlaybackMode="LIVE_REPLAY",
            HLSFragmentSelector={
                'FragmentSelectorType': 'PRODUCER_TIMESTAMP',
                'TimestampRange': {
                    'StartTimestamp': result['InputInformation']['KinesisVideo']['ProducerTimestamp']
                }
            }
        )['HLSStreamingSessionURL']
        vcap = cv2.VideoCapture(url)
        final_key = 'kvs1_'
        s3_client = boto3.client('s3')
        bucket = "rekognitionb1"
        while(True):
            # Capture frame-by-frame
            ret, frame = vcap.read()

            if frame is not None:
                # Display the resulting frame
                vcap.set(1, int(vcap.get(cv2.CAP_PROP_FRAME_COUNT) / 2) - 1)
                final_key = final_key + time.strftime("%Y%m%d-%H%M%S") + '.jpg'
                cv2.imwrite('/tmp/' + final_key, frame)
                s3_client.upload_file('/tmp/' + final_key, bucket, final_key)
                vcap.release()
                print('Image uploaded')
                break
            else:
                print("Frame is None")
                break

        # When everything done, release the capture
        vcap.release()
        cv2.destroyAllWindows()
        location = boto3.client('s3').get_bucket_location(Bucket=bucket)['LocationConstraint']
        s3ImageLink = "https://%s.s3-%s.amazonaws.com/%s" % (bucket, location, final_key)
        print("s3ImageLink ====" + s3ImageLink)

        snsClient = boto3.client('sns')
        dynamodb = boto3.resource('dynamodb', region_name='us-west-2')
        visitorsTable = dynamodb.Table('cc-smart-door-visitors')
        unknownFace = True
        for face in faceResponse:
            for matchedFace in face["MatchedFaces"]:
                print("matchedFace ===")
                print(matchedFace)
                print(matchedFace['Face']['FaceId'])
                faceId = matchedFace['Face']['FaceId']
                response = visitorsTable.query(KeyConditionExpression=Key('faceId').eq(faceId))
                print("response =====")
                print(response['Items'])
                if len(response['Items']) > 0:
                    phoneNumber = response['Items'][0]['phone_number']
                    passcodeTable = dynamodb.Table('cc-smart-door-passcodes')
                    currentEpochTime = int(time.time())
                    print("currentEpochTime ============")
                    print(currentEpochTime)
                    passcodeResponse = passcodeTable.query(KeyConditionExpression=Key('phone_number').eq(phoneNumber), FilterExpression=Key('ttl').gt(currentEpochTime))
                    if len(passcodeResponse['Items']) > 0:
                        otp = passcodeResponse['Items'][0]['passcode']
                    else:
                        otp = randint(10**4, 10**5 - 1)
                        response = passcodeTable.put_item(
                            Item={
                                "passcode": otp,
                                "phone_number": phoneNumber,
                                "ttl": int(time.time() + 5 * 60)
                            })

                    snsClient.publish(
                        PhoneNumber=phoneNumber,
                        Message="Please visit https://smartdoorb1.s3-us-west-2.amazonaws.com/views/html/wp2.html?phone=" + phoneNumber + " to get access to the door. Your otp is " + str(otp) + " and will expire in 5 minutes.")
                    unknownFace = False
                break
        if unknownFace:
            print("unknownFace =")
            snsClient.publish(
                PhoneNumber='+16315683216',
                Message="A new visitor has arrived. Use the link https://smartdoorb1.s3-us-west-2.amazonaws.com/views/html/wp1.html?image=" + s3ImageLink + " to approve or deny access.")
            unknownFace = False
        # print("dshdhjdjs==========")

    return 'Successfully processed {} records.'.format(len(event['Records']))

'''
import logging
import base64
import json
import boto3
import os
import random as r
import time
from decimal import Decimal 

s3_client = boto3.client('s3')
s3_resource = boto3.resource('s3')

smsClient = boto3.client('sns')

dynamo_resource = boto3.resource('dynamodb')

dynamo_visitors_table = dynamo_resource.Table("visitors")
dynamo_passcodes_table = dynamo_resource.Table("passcodes")


def lambda_handler(event, context):
    
    logging.info("API CALLED. EVENT IS:{}".format(event))
    
    print("Data streaming")
    data = event['Records'][0]['kinesis']['data']
    print(base64.b64decode(data))
    json_data = json.loads(base64.b64decode(data).decode('utf-8'))
    stream_name="smart-door-stream"
    print('JSON DATA',json_data)
    
    
    smsClient = boto3.client('sns')
    mobile = "6466230205"
    
	faceId='123'
    face_search_response = json_data['FaceSearchResponse']
    if face_search_response is None:
        return ("No one at the door")
    else:
        matched_face = json_data['FaceSearchResponse'][0]['MatchedFaces']
    
    if face_search_response is not None and ( matched_face is None or len(matched_face)==0):
        fragmentNumber= json_data['InputInformation']['KinesisVideo']['FragmentNumber']
        fileName,faceId=store_image(stream_name,fragmentNumber, None)
    else:
        image_id = json_data['FaceSearchResponse'][0]['MatchedFaces'][0]['Face']['ImageId']
        print('IMAGEID',image_id)
        faceId = json_data['FaceSearchResponse'][0]['MatchedFaces'][0]['Face']['FaceId']
        print('FACEID',faceId)

    key = {'faceId' : faceId}   
    visitors_response = dynamo_visitors_table.get_item(Key=key)
    
    keys_list = list(visitors_response.keys())
    
    otp=""
    for i in range(4):
        otp+=str(r.randint(1,9))
    
    if('Item' in keys_list):
        
        phone_number_visitor = visitors_response['Item']['phone']
        face_id_visitor = visitors_response['Item']['faceId']
        
        
        
        visitors_name = visitors_response['Item']['name']
        visitors_photo = visitors_response['Item']['photo']
        photo={'objectKey':'updatedKey' , 'bucket' : 'myBucket', 'createdTimestamp' : str(time.ctime(time.time()))}
        visitors_photo.append(photo)
        
        my_visitor_entry = {'faceId' : face_id_visitor , 'name' : visitors_name , 'phone' : phone_number_visitor , 'photo' : visitors_photo}
        dynamo_visitors_table.put_item(Item=my_visitor_entry)
        
        
        
        my_string = {'faceId' : face_id_visitor, 'otp': otp, 'expiration' : str(int(time.time() + 300))}
        dynamo_passcodes_table.put_item(Item=my_string)
        
    else:
        phone_number_owner = '6466230205'
        link_visitor_image = 'https://smart-door-trr.s3.amazonaws.com/' + filename
        
        
        ####saqib changes start
        link_visitor_details_form = 'https://smart-door-trr.s3.amazonaws.com/WebPage_Vistor_Info.html?filename='+fileName+"&faceid="+faceId
        ###saqib changes end
        
        print("URLs sent to Owner: ")
        # sendMessageToOwner(phone_number_owner, link)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }

def sendOtpToVisitor(phone_number, otp):
    
    message_visitor = "Hello, here is your one time password, "
    message_visitor += str(otp)
    smsClient.publish(PhoneNumber="+1"+phone_number,Message=message_visitor)
    
def sendMessageToOwner(phone_number, link):
    
    message_owner = "Hello, here is the link for your visitor image, "
    message_owner += str(link)
    
    smsClient.publish(PhoneNumber="+1"+phone_number,Message=message_owner)
	
def store_image(stream_name, fragmentNumber,faceId):
    kvs_client = boto3.client('kinesis-video-archived-media')
    s3_client = boto3.client('s3')
    rekClient=boto3.client('rekognition')
    
    kvs = boto3.client("kinesisvideo")
    
    endpoint = kvs.get_data_endpoint(
        APIName="GET_MEDIA_FOR_FRAGMENT_LIST",
        StreamName=stream_name
    )['DataEndpoint']
    print("Kinesis Data endpoint: ",endpoint)
    kvam = boto3.client("kinesis-video-archived-media", endpoint_url=endpoint)
    
    
    kvs_stream = kvs_client.get_media_for_fragment_list(
    StreamName=stream_name,
    Fragments=[
        fragmentNumber,
    ])
    collectionId="smart-door"
    print("KVS Stream: ",kvs_stream)
    
    with open('/tmp/stream.mkv', 'wb') as f:
        streamBody = kvs_stream['Payload'].read(1024*16384) 
        f.write(streamBody)
        cap = cv2.VideoCapture('/tmp/stream.mkv')
        
        total=int(count_frames_manual(cap)/2)
        cap.set(2,total);
        ret, frame = cap.read() 
        cv2.imwrite('/tmp/frame.jpg', frame)
        
        if(faceId is None):
            faceId=index_image(frame, collectionId,fragmentNumber)
        fileName= faceId+'-'+fragmentNumber+'.jpg'
        s3_client.upload_file(
            '/tmp/frame.jpg',
            'smart-door-trr', 
            fileName
        )
        cap.release()
        print('Image uploaded')
        return fileName, faceId

def index_image(frame, collectionId, fragmentNumber):
     
    retval, buffer = cv2.imencode('.jpg', frame)
    response=rekClient.index_faces(CollectionId=collectionId,
    Image={
    'Bytes': buffer,
    },
    ExternalImageId=fragmentNumber,
    DetectionAttributes=['ALL'])
    
    print('New Response',response)
    faceId=''
    for faceRecord in response['FaceRecords']:
        faceId = faceRecord['Face']['FaceId']

def count_frames_manual(video):
	total = 0
	while True:
		(grabbed, frame) = video.read()
		if not grabbed:
			break
		total += 1
	return total