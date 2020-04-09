from __future__ import print_function
import logging
import base64
import json
import boto3
import time
import cv2
from boto3.dynamodb.conditions import Key
from random import randint
from decimal import Decimal

REGION = 'us-east-1'
DB_VISITOR = 'visitors'
DB_PASSCODE = 'passcodes'
DB_MESSAGE = 'messages'
DEFAULT_PHONE_NUMBER = '+13474051241'
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
dynamodb_messages = dynamodb.Table(DB_MESSAGE)


def valid_phone(phone_number):
    # valid phone sample: E.164 format, +11234567890
    if not isinstance(phone_number, str):
        print('phone number invalid, input should be string')
        return False
    if phone_number[0] != '+':
        print('phone number invalid, start with "+"')
        return False
    if phone_number[1] != '1':
        print('phone number invalid, other countries not supported')
        return False
    if len(phone_number) != 12:
        print('phone number invalid, digits length 11')
        return False

    response_messages = dynamodb_messages.query(KeyConditionExpression=Key('phoneNumber').eq(phone_number))
    if len(response_messages['Items']) == 0:
        dynamodb_messages.put_item(
            Item={'phoneNumber': phone_number,
                  'updateTime': Decimal.from_float(time.time())})
    else:
        time_passed = time.time() - float(response_messages['Items'][0]['updateTime'])
        if time_passed < 60:
            print('7--. SNS suspends. Message to number ' + phone_number + ' sent less than 30s ago, SNS suspends. Time passed: ' + str(time_passed))
            return False
        dynamodb_messages.update_item(
            Key={'phoneNumber': phone_number},
            UpdateExpression='set updateTime=:t',
            ExpressionAttributeValues={':t': Decimal.from_float(time.time())})
    # message sent too frequently
    return True


def lambda_handler(event, context):
    logging.info("API CALLED. EVENT IS:{}".format(event))
    time_start = time.time()
    personDetected = False
    for record in event['Records']:
        ###################
        # decode KDS data
        if personDetected is True:
            break
        data_decode = base64.b64decode(record['kinesis']['data']).decode('utf-8')
        data_json = json.loads(data_decode)
        data_face_search_response = data_json['FaceSearchResponse']
        data_input_info = data_json['InputInformation']

        print('1. KDS Data input info: ', data_input_info)
        if len(data_face_search_response) > 0:
            personDetected = True
            print('2. KDS FaceSearchResponse not empty ', json.dumps(data_face_search_response))
        else:
            print('2. KDS FaceSearchResponse is empty, no face detected, skip this record')
            continue
        ###################

        ###################
        # upload KVS stream capture to S3
        # Grab the endpoint from GetDataEndpoint
        endpoint = kvs.get_data_endpoint(
            APIName='GET_HLS_STREAMING_SESSION_URL',
            StreamARN=STREAM_ARN
        )['DataEndpoint']
        print('3. KVS Stream Endpoint: ', endpoint)
        # Grab the HLS Stream URL from the endpoint
        kvam = boto3.client('kinesis-video-archived-media', endpoint_url=endpoint)
        url = kvam.get_hls_streaming_session_url(
            StreamARN=STREAM_ARN,
            PlaybackMode="LIVE",
            HLSFragmentSelector={'FragmentSelectorType': 'SERVER_TIMESTAMP'}
        )['HLSStreamingSessionURL']
        print('4. KVS HLS streaming session URL: ', url)
        cap = cv2.VideoCapture(url)
        file_name = ''
        while(True):
            # Capture frame-by-frame
            ret, frame = cap.read()
            if frame is not None:
                # Display the resulting frame
                cap.set(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT) / 2) - 1)
                file_name = '/tmp/' + FRAME_KEY + time.strftime("%Y%m%d-%H%M%S") + '.jpg'
                cv2.imwrite(file_name, frame)
                print('5. KVS Frame captured, written to local address: ' + file_name)
                break
            else:
                print("5. KVS Frame is None")
                continue
        # release capture
        cap.release()
        cv2.destroyAllWindows()

        s3_client.upload_file(file_name, BUCKET, file_name[1:])
        S3_image_link = 'https://' + BUCKET + '.s3.amazonaws.com' + file_name
        print('6. KVS frame uploaded to S3, BUCKET: ' + BUCKET + ', file name: ' + file_name + ', S3_image_link: ' + S3_image_link)
        ###################

        ###################
        # sends SNS message based on face detection results from KDS
        # ['FaceSearchResponse'][itr]['MatchedFaces'][itr]['Face']['ImageId/FaceId']
        matched_face_found = False
        for face in data_face_search_response:
            for matched_face in face["MatchedFaces"]:
                print('7-1. KDS matched face found: ', matched_face)
                face_id = matched_face['Face']['FaceId']
                print('7-2. DynamoDB search matched KDS face id : ' + face_id + ' in visitors table')
                response_visitors = dynamodb_visitors.query(KeyConditionExpression=Key('faceId').eq(face_id))
                if len(response_visitors['Items']) > 0:
                    print('7-3. DynamoDB visitor with matched faceId found:', response_visitors)
                    visitors_phone_number = response_visitors['Items'][0]['phoneNumber']
                    print('7-4. DynamoDB search phone number :' + visitors_phone_number + ' in passcodes table')
                    response_passcodes = dynamodb_passcodes.query(
                        KeyConditionExpression=Key('phoneNumber').eq(visitors_phone_number),
                        FilterExpression=Key('ttl').gt(int(time.time())))
                    if len(response_passcodes['Items']) > 0:
                        print('7-5. DynamoDB passcodes with visitor phone number found: ', response_passcodes['Items'])
                        otp = response_passcodes['Items'][0]['passcode']
                        print('7-6. DynamoDB exists visitor phone number: ' + visitors_phone_number + ', passcode: ' + str(otp))
                    else:
                        print('7-5. DynamoDB passcodes with visitor phone number not found, response: ', response_passcodes)
                        otp = randint(10**5, 10**6 - 1)
                        ttl = int(time.time() + 5 * 60)
                        dynamodb_passcodes.put_item(
                            Item={
                                'passcode': otp,
                                'phoneNumber': visitors_phone_number,
                                'ttl': ttl
                            })
                        print('7-6. DynamoDB new otp uploaded to passcodes table: ' + str(otp) + ', ttl: ' + str(ttl) + ', phone number: ' + visitors_phone_number)
                    if valid_phone(visitors_phone_number):
                        msg = 'Please visit https://' + S3_NAME + '.s3-' + REGION \
                            + '.amazonaws.com/views/html/wp2.html?phone=' + visitors_phone_number \
                            + ' to get access to the door. Your otp is ' + str(otp) + ' and will expire in 5 minutes.'
                        print('7-7. SNS sends known face message: ' + msg)
                        sns_client.publish(
                            PhoneNumber=visitors_phone_number,
                            Message=msg)
                else:
                    print('7-3. KDS matched faceId not found in DynamoDB visitors table, response: ', response_visitors)
                    if valid_phone(DEFAULT_PHONE_NUMBER):
                        msg = 'A new visitor has arrived. Use the link https://' + S3_NAME  \
                            + '.s3-' + REGION + '.amazonaws.com/views/html/wp1.html?image=' \
                            + S3_image_link + ' to approve or deny access.'
                        print('7-4. SNS sends unknown face to default phone number: ' + DEFAULT_PHONE_NUMBER + ', message: ' + msg)
                        sns_client.publish(
                            PhoneNumber=DEFAULT_PHONE_NUMBER,
                            Message=msg)
                    else:
                        print('7-4. Default phone number not valid, SNS suspends.')
                matched_face_found = True
                break
        if not matched_face_found:
            msg = 'A new visitor has arrived. Use the link https://' + S3_NAME  \
                + '.s3-' + REGION + '.amazonaws.com/views/html/wp1.html?image=' \
                + S3_image_link + ' to approve or deny access.'
            if valid_phone(DEFAULT_PHONE_NUMBER):
                print('7. KDS no matched faceId, SNS sends unknown face to default phone number: ' + DEFAULT_PHONE_NUMBER + ', message: ' + msg)
                sns_client.publish(
                    PhoneNumber=DEFAULT_PHONE_NUMBER,
                    Message=msg)
                matched_face_found = True
            else:
                print('7--. KDS no matched faceId, default phone number not valid, SNS suspends.')
    print('8. Lambda <door_lambda1> ends, running time: ' + str(time.time() - time_start) + 's')
    return {
        'statusCode': 200,
        'body': json.dumps('Successfully processed {} records.'.format(len(event['Records'])))
    }
