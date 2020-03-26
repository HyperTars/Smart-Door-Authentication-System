from __future__ import print_function

import logging
import base64
import json
import boto3
import random
import os
import time
import sys
import cv2
from boto3.dynamodb.conditions import Key
from decimal import Decimal

DB_VISITOR = 'visitors'
DB_PASSCODE = 'passcodes'
DB_REGION = 'us-east-1'
PHONE_NUMBER = 'XXX-XXX-XXXX'
STREAM_NAME = 'LiveRekognitionVideoAnalysisBlog'
STREAM_ARN = 'arn:aws:kinesisvideo:us-west-2:655546244197:stream/LiveRekognitionVideoAnalysisBlog/1572919264579'
FRAME_KEY = 'kvs_frame_'
BUCKET = "rekognitionb1"
S3_NAME = 'smart-door'

s3_client = boto3.client('s3')
s3_resource = boto3.resource('s3')
sns_client = boto3.client('sns')
kvs = boto3.client("kinesisvideo")
dynamodb = boto3.resource('dynamodb', region_name=DB_REGION)
kvs_client = boto3.client('kinesis-video-archived-media')
rek_client=boto3.client('rekognition')

dynamodb_visitors_table = dynamodb.Table(DB_VISITOR)
dynamodb_passcodes_table = dynamodb.Table(DB_PASSCODE)

sys.path.insert(1, '/opt')


def lambda_handler(event, context):
    logging.info("API CALLED. EVENT IS:{}".format(event))

    personDetected = False
    for record in event['Records']:
        # decode Kinesis data
        if personDetected is True:
            break
        data_decode = base64.b64decode(record['kinesis']['data']).decode('utf-8')
        data_json = json.loads(data_decode)
        data_face_search_response = data_json['FaceSearchResponse']
        data_input_info = data_json['InputInformation']

        print(data_input_info)
        if len(data_face_search_response) > 0:
            personDetected = True
            print("FaceSearchResponse not empty = " + json.dumps(data_face_search_response))
        else:
            continue
        frag_id = data_input_info['KinesisVideo']['FragmentNumber']
        print("frag id = ", frag_id)

        ########## store image ##########
        # Grab the endpoint from GetDataEndpoint
        endpoint = kvs.get_data_endpoint(
            APIName="GET_HLS_STREAMING_SESSION_URL",
            StreamName=STREAM_NAME
        )['DataEndpoint']
        print('Kinesis Data Endpoint: ', endpoint)

        # Grab the HLS Stream URL from the endpoint
        kvam = boto3.client('kinesis-video-archived-media', endpoint_url=endpoint)
        url = kvam.get_hls_streaming_session_url(
            StreamName=STREAM_NAME,
            PlaybackMode="LIVE_REPLAY",
            HLSFragmentSelector={
                'FragmentSelectorType': 'PRODUCER_TIMESTAMP',
                'TimestampRange': {
                    'StartTimestamp': data_input_info['KinesisVideo']['ProducerTimestamp']
                }
            }
        )['HLSStreamingSessionURL']
        cap = cv2.VideoCapture(url)

        while(True):
            # Capture frame-by-frame
            ret, frame = cap.read()

            if frame is not None:
                # Display the resulting frame
                cap.set(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT) / 2) - 1)
                file_name = '/tmp/' + FRAME_KEY + time.strftime("%Y%m%d-%H%M%S") + '.jpg'
                cv2.imwrite(file_name, frame)
                s3_client.upload_file(file_name, BUCKET, file_name)
                print('Image uploaded')
                break
            else:
                print("Frame is None")
                break

        # release capture
        cap.release()
        cv2.destroyAllWindows()
        location = boto3.client('s3').get_bucket_location(Bucket=BUCKET)['LocationConstraint']
        s3_image_link = "https://%s.s3-%s.amazonaws.com/%s" % (BUCKET, location, file_name)
        print('s3_image_link: ' + s3_image_link)




        unknown_face = True
        for face in data_face_search_response:
            for matched_face in face["MatchedFaces"]:
                print("matched_face ===")
                print(matched_face)
                print(matched_face['Face']['FaceId'])
                faceId = matched_face['Face']['FaceId']
                response = dynamodb_visitors_table.query(KeyConditionExpression=Key('faceId').eq(faceId))
                print("response =====")
                print(response['Items'])
                if len(response['Items']) > 0:
                    phoneNumber = response['Items'][0]['phone_number']
                    currentEpochTime = int(time.time())
                    print("currentEpochTime ============")
                    print(currentEpochTime)
                    passcodeResponse = dynamodb_passcodes_table.query(KeyConditionExpression=Key('phone_number').eq(phoneNumber), FilterExpression=Key('ttl').gt(currentEpochTime))
                    if len(passcodeResponse['Items']) > 0:
                        otp = passcodeResponse['Items'][0]['passcode']
                    else:
                        otp = randint(10**4, 10**5 - 1)
                        response = dynamodb_passcodes_table.put_item(
                            Item={
                                'passcode': otp,
                                'phone_number': phoneNumber,
                                'ttl': int(time.time() + 5 * 60)
                            })

                    sns_client.publish(
                        PhoneNumber=phoneNumber,
                        Message='Please visit https://' + S3_NAME + '.s3-us-west-2.amazonaws.com/views/html/wp2.html?phone=' + phoneNumber + ' to get access to the door. Your otp is ' + str(otp) + ' and will expire in 5 minutes.')
                    unknown_face = False
                break
        if unknown_face:
            print("unknown_face =")
            sns_client.publish(
                PhoneNumber=PHONE_NUMBER,
                Message='A new visitor has arrived. Use the link https://' + S3_NAME + 'smartdoorb1.s3-us-west-2.amazonaws.com/views/html/wp1.html?image=' + s3_image_link + ' to approve or deny access.')
            unknown_face = False

    return 'Successfully processed {} records.'.format(len(event['Records']))
