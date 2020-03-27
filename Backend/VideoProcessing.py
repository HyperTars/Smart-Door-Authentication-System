from __future__ import print_function
import logging
import base64
import json
import boto3
import os
import time
import sys
import cv2
from boto3.dynamodb.conditions import Key
from random import randint

DB_VISITOR = 'visitors'
DB_PASSCODE = 'passcodes'
DB_REGION = 'us-east-1'
PHONE_NUMBER_DEFAULT = 'XXX-XXX-XXXX'
STREAM_NAME = 'MyKVS'
STREAM_ARN = 'arn:aws:kinesisvideo:us-east-1:178190676612:stream/MyKVS/1585017025587'
STREAM_KEY_ARN = 'arn:aws:kms:us-east-1:178190676612:key/c3cf8539-ad7e-4ada-81b8-f440cd6d5af2'
STREAM_KEY_ID = 'c3cf8539-ad7e-4ada-81b8-f440cd6d5af2'
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

dynamodb_visitors = dynamodb.Table(DB_VISITOR)
dynamodb_passcodes = dynamodb.Table(DB_PASSCODE)

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

        print('Data input info: \n', data_input_info)
        if len(data_face_search_response) > 0:
            personDetected = True
            print('FaceSearchResponse not empty = ' + json.dumps(data_face_search_response))
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
        s3_image_link = 'https://%s.s3-%s.amazonaws.com/%s' % (BUCKET, location, file_name)
        print('S3_image_link: ' + s3_image_link)

        # face detect
        # ['FaceSearchResponse'][itr]['MatchedFaces'][itr]['Face']['ImageId/FaceId']
        unknown_face = True
        for face in data_face_search_response:
            for matched_face in face["MatchedFaces"]:
                image_id = matched_face['Face']['ImageId']
                face_id = matched_face['Face']['FaceId']
                print('Matched_face: \n', matched_face)
                print('Matched_face_image_id: \n', image_id)
                print('Matched_face_face_id: \n', face_id)
                response_visitors = dynamodb_visitors.query(
                    KeyConditionExpression=Key('face_id').eq(face_id))
                print('Visitor_response: \n', response_visitors)
                # print(response_visitors['Items'])
                if len(response_visitors['Items']) > 0:
                    phone_number = response_visitors['Items'][0]['phone_number']
                    print('Current Time: ', int(time.time()))
                    response_passcodes = dynamodb_passcodes.query(
                        KeyConditionExpression=Key('phone_number').eq(phone_number),
                        FilterExpression=Key('ttl').gt(int(time.time())))
                    if len(response_passcodes['Items']) > 0:
                        otp = response_passcodes['Items'][0]['passcode']
                    else:
                        otp = randint(10**5, 10**6 - 1)
                        response_visitors = dynamodb_passcodes.put_item(
                            Item={
                                'passcode': otp,
                                'phone_number': phone_number,
                                'ttl': int(time.time() + 5 * 60)
                            })

                    sns_client.publish(
                        PhoneNumber=phone_number,
                        Message='Please visit https://' + S3_NAME + '.s3-us-west-2.amazonaws.com/views/html/wp2.html?phone=' + phone_number + ' to get access to the door. Your otp is ' + str(otp) + ' and will expire in 5 minutes.')
                    unknown_face = False
                break
        if unknown_face:
            print("unknown_face =")
            sns_client.publish(
                PhoneNumber=PHONE_NUMBER_DEFAULT,
                Message='A new visitor has arrived. Use the link https://' + S3_NAME + 'smartdoorb1.s3-us-west-2.amazonaws.com/views/html/wp1.html?image=' + s3_image_link + ' to approve or deny access.')
            unknown_face = False

    return {
        'statusCode': 200,
        'body': json.dumps('Successfully processed {} records.'.format(len(event['Records'])))
    }
