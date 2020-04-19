Install OpenCV for Python
pip3 install opencv-python

## Install OpenCV for Lambda
**2 OpenCV as a layer, can edit lambda**
**./opencv_aws_lambda**

FUNCTION_NAME=door_lambda1
ACCOUNT_ID=178190676612
LAMBDA_LAYERS_BUCKET=smart-door-system
LAYER_NAME=cv2
aws s3 mb s3://$LAMBDA_LAYERS_BUCKET
aws s3 cp cv2-python37.zip s3://$LAMBDA_LAYERS_BUCKET
aws lambda publish-layer-version --layer-name $LAYER_NAME --description "Open CV" --content S3Bucket=$LAMBDA_LAYERS_BUCKET,S3Key=cv2-python37.zip --compatible-runtimes python3.7


zip door_lambda1.zip door_lambda1.py

ZIPFILE=allinone.zip
unzip cv2-python37.zip 
cp door_lambda1.py python/lib/python3.7/site-packages/
cd python/lib/python3.7/site-packages/
zip -r9 ../../../../$ZIPFILE .
cd -

ROLE_NAME=
FUNCTION_NAME=door_lambda1
ACCOUNT_ID=178190676612
BUCKET_NAME=smart-door-system
aws s3 mb s3://$BUCKET_NAME
aws s3 cp door_lambda1.zip s3://$BUCKET_NAME
aws lambda create-function --function-name $FUNCTION_NAME --timeout 20 --role arn:aws:iam::${ACCOUNT_ID}:role/$ROLE_NAME --handler door_lambda1.lambda_handler --region us-east-1 --runtime python3.7  --code S3Bucket="$BUCKET_NAME",S3Key="door_lambda1.zip"

aws lambda update-function-configuration --function-name $FUNCTION_NAME --layers arn:aws:lambda:us-east-1:178190676612:layer:cv2:3