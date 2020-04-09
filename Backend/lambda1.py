from __future__ import print_function
import logging
import base64
import json
import boto3
import time
import cv2
from boto3.dynamodb.conditions import Key
from random import randint

REGION = 'us-east-1'
DB_VISITOR = 'visitors'
DB_PASSCODE = 'passcodes'
PHONE_NUMBER_DEFAULT = ''
STREAM_NAME = 'MyKVS'
STREAM_ARN = 'arn:aws:kinesisvideo:us-east-1:178190676612:stream/MyKVS/1585017025587'
STREAM_KEY_ARN = 'arn:aws:kms:us-east-1:178190676612:key/c3cf8539-ad7e-4ada-81b8-f440cd6d5af2'
STREAM_KEY_ID = 'c3cf8539-ad7e-4ada-81b8-f440cd6d5af2'
FRAME_KEY = 'kvs_frame_'
BUCKET = "smart-door-system"
S3_NAME = 'smart-door-system'

s3_client = boto3.client('s3')
s3_resource = boto3.resource('s3')
sns_client = boto3.client('sns')
kvs = boto3.client("kinesisvideo")
dynamodb = boto3.resource('dynamodb', region_name=REGION)
kvs_client = boto3.client('kinesis-video-archived-media')

dynamodb_visitors = dynamodb.Table(DB_VISITOR)
dynamodb_passcodes = dynamodb.Table(DB_PASSCODE)


def lambda_handler(event, context):
    logging.info("API CALLED. EVENT IS:{}".format(event))
    time_start = time.time()
    personDetected = False
    for record in event['Records']:
        # decode Kinesis data
        if personDetected is True:
            break
        data_decode = base64.b64decode(record['kinesis']['data']).decode('utf-8')
        data_json = json.loads(data_decode)
        data_face_search_response = data_json['FaceSearchResponse']
        data_input_info = data_json['InputInformation']

        print('1. KDS Data input info: ', data_input_info)
        if len(data_face_search_response) > 0:
            personDetected = True
            print('2. KDS FaceSearchResponse not empty ' + json.dumps(data_face_search_response))
        else:
            print('2. KDS FaceSearchResponse is empty, skip this record')
            continue

        # store image
        # Grab the endpoint from GetDataEndpoint
        endpoint = kvs.get_data_endpoint(
            APIName='GET_HLS_STREAMING_SESSION_URL',
            StreamARN=STREAM_ARN
        )['DataEndpoint']
        print('3. KVS Data Endpoint: ', endpoint)
        # Grab the HLS Stream URL from the endpoint
        kvam = boto3.client('kinesis-video-archived-media', endpoint_url=endpoint)
        url = kvam.get_hls_streaming_session_url(
            StreamARN=STREAM_ARN,
            PlaybackMode="LIVE",
            HLSFragmentSelector={'FragmentSelectorType': 'SERVER_TIMESTAMP'}
        )['HLSStreamingSessionURL']
        print('4. KVS HLSStreamingSessionURL: ', url)
        cap = cv2.VideoCapture(url)
        file_name = ''
        while(True):
            # Capture frame-by-frame
            ret, frame = cap.read()
            if frame is not None:
                # Display the resulting frame
                cap.set(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT) / 2) - 1)
                file_name = 'tmp/' + FRAME_KEY + time.strftime("%Y%m%d-%H%M%S") + '.jpg'
                cv2.imwrite('/' + file_name, frame)
                print('5. KVS Frame captured, written to local address: /' + file_name)
                break
            else:
                print("5. KVS Frame is None, skip")
                break
        # release capture
        cap.release()
        cv2.destroyAllWindows()

        s3_client.upload_file('/' + file_name, BUCKET, file_name)
        S3_image_link = 'https://' + BUCKET + '.s3.amazonaws.com/' + file_name
        print('6. KVS frame uploaded to S3, BUCKET: ' + BUCKET + ', file name: /' + file_name + ', S3_image_link: ' + S3_image_link)

        # face detect
        # ['FaceSearchResponse'][itr]['MatchedFaces'][itr]['Face']['ImageId/FaceId']
        unknown_face = True
        for face in data_face_search_response:
            for matched_face in face["MatchedFaces"]:
                image_id = matched_face['Face']['ImageId']
                face_id = matched_face['Face']['FaceId']
                print('7-1. KDS face matched: ', matched_face)
                print('7-2. KDS face matched - image id: ', image_id)
                print('7-3. KDS face matched - face id: ', face_id)
                response_visitors = dynamodb_visitors.query(
                    KeyConditionExpression=Key('faceId').eq(face_id))
                print('7-4. DynamoDB visitors response: ', response_visitors)
                if len(response_visitors['Items']) > 0:
                    phone_number = response_visitors['Items'][0]['phone_number']
                    response_passcodes = dynamodb_passcodes.query(
                        KeyConditionExpression=Key('phoneNumber').eq(phone_number),
                        FilterExpression=Key('ttl').gt(int(time.time())))
                    print('7-5. DynamoDB passcodes response: ', response_passcodes)
                    if len(response_passcodes['Items']) > 0:
                        otp = response_passcodes['Items'][0]['passcode']
                        print('7-6. DynamoDB passcode exists, otp:', str(otp))
                    else:
                        otp = randint(10**5, 10**6 - 1)
                        ttl = int(time.time() + 5 * 60)
                        print('7-6. DynamoDB passcode not exists, upload new otp: ' + str(otp) + ', ttl: ' + ttl + ', phone number: ' + phone_number)
                        response_visitors = dynamodb_passcodes.put_item(
                            Item={
                                'passcode': otp,
                                'phone_number': phone_number,
                                'ttl': ttl
                            })
                    msg = 'Please visit https://' + S3_NAME + '.s3-' + REGION \
                        + '.amazonaws.com/views/html/wp2.html?phone=' + phone_number \
                        + ' to get access to the door. Your otp is ' + str(otp) + ' and will expire in 5 minutes.'
                    print('7-7. SNS message_known_face to phone number: ' + phone_number + ', message: ' + msg)
                    sns_client.publish(
                        PhoneNumber=phone_number,
                        Message=msg)
                    unknown_face = False
                else:
                    print('7-5. KDS faceId not in DyanoDB visitors table, take it as unknown face.')
                    msg = 'A new visitor has arrived. Use the link https://' + S3_NAME  \
                        + '.s3-' + REGION + '.amazonaws.com/views/html/wp1.html?image=' \
                        + S3_image_link + ' to approve or deny access.'
                    if (PHONE_NUMBER_DEFAULT != ''):
                        print('7-6. KDS faceId not in DyanoDB visitors table, SNS message_unknown_face to phone number: ' + PHONE_NUMBER_DEFAULT + ', message: ' + msg)
                        sns_client.publish(
                            PhoneNumber=PHONE_NUMBER_DEFAULT,
                            Message=msg)
                        unknown_face = False
                    else:
                        print('7-6. KDS faceId not in DyanoDB visitors table, default phone number not defined, SNS suspends.')
                        unknown_face = False
                break
        if unknown_face:
            msg = 'A new visitor has arrived. Use the link https://' + S3_NAME  \
                + '.s3-' + REGION + '.amazonaws.com/views/html/wp1.html?image=' \
                + S3_image_link + ' to approve or deny access.'
            if (PHONE_NUMBER_DEFAULT != ''):
                print('7. KDS no matched faceId, SNS message_unknown_face to phone number: ' + PHONE_NUMBER_DEFAULT + ', message: ' + msg)
                sns_client.publish(
                    PhoneNumber=PHONE_NUMBER_DEFAULT,
                    Message=msg)
                unknown_face = False
            else:
                print('7. KDS no matched faceId, default phone number not defined, SNS suspends.')
    print('8. Lambda <door_lambda1> ends, time: ' + str(time.time() - time_start) + 's')
    return {
        'statusCode': 200,
        'body': json.dumps('Successfully processed {} records.'.format(len(event['Records'])))
    }
