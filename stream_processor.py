import boto3

client = boto3.client('rekognition')

# create stream processor
# response = client.create_stream_processor(
#     Input={
#         'KinesisVideoStream': {
#             'Arn': 'arn:aws:kinesisvideo:us-east-1:178190676612:stream/MyKVS/1585017025587'
#         }
#     },
#     Output={
#         'KinesisDataStream': {
#             'Arn': 'arn:aws:kinesis:us-east-1:178190676612:stream/AmazonRekognitionMyKDS'
#         }
#     },
#     Name='MyStreamProcessor',
#     Settings={
#         'FaceSearch': {
#             'CollectionId': 'MyCollection',
#             'FaceMatchThreshold': 50
#         }
#     },
#     RoleArn='arn:aws:iam::178190676612:role/Rekognition'
# )

# start stream processor
# response = client.start_stream_processor(
#     Name='MyStreamProcessor'
# )


response = client.describe_stream_processor(
    Name='MyStreamProcessor'
)

# response = client.stop_stream_processor(
#     Name='MyStreamProcessor'
# )

# response = client.delete_stream_processor(
#     Name='MyStreamProcessor'
# )
print(response)