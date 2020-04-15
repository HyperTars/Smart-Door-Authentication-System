import * as AWS from 'aws-sdk';
import {
    PartialUnknown,
    VisitorRequest, DoorResponse,
    passcodeTableName, PasscodeTableEntry,
    awsConfig,
    visitorTableName, visitorPhoneNumberIndexName, VisitorTableEntry
} from './api';

AWS.config.update(awsConfig);
const dynamodb = new AWS.DynamoDB.DocumentClient();

const raise = <TError, TState extends { error?: TError }>(state: TState, message: TError) => {
    state.error = message;
    return state as TState & { error: TError };
};

const handler = async (event: unknown) => {
    const ret: DoorResponse = { status: 'closed' };

    if (typeof event !== 'object' || !event) return raise(ret, 'ERR_REQUEST_MALFORMED');

    const { phoneNumber, passcode, status = 'open' } = event as PartialUnknown<VisitorRequest>;

    if (typeof phoneNumber === 'undefined' && typeof passcode === 'undefined') {
        const { Count } = await dynamodb.scan({
            TableName: passcodeTableName,
            Limit: 10,
            Select: 'COUNT',
        }).promise();

        if (Count === undefined) return raise(ret, 'ERR_PENDING_UNKOWN');

        ret.pending = Count;
        return ret;
    }
    else {
        if (typeof phoneNumber !== 'string') return raise(ret, 'ERR_PHONE_NUMBER_INVALID');
        if (!/^\+1\d{10}$/.test(phoneNumber)) return raise(ret, 'ERR_PHONE_NUMBER_INVALID');

        if (typeof passcode !== 'number') return raise(ret, 'ERR_PASSCODE_INVALID');
        const Response = await dynamodb.get({
            TableName: passcodeTableName,
            Key: { phoneNumber },
        }).promise();
        if (!Response.Item) return raise(ret, 'ERR_PHONE_NUMBER_NOT_FOUND');

        const Item = Response.Item as PasscodeTableEntry;
        if (passcode !== Item.passcode) return raise(ret, 'ERR_PASSCODE_INCORRECT');

        await dynamodb.delete({
            TableName: passcodeTableName,
            Key: { phoneNumber },
        }).promise();

        if (status !== 'open' && status !== 'closed') return raise(ret, 'ERR_STATUS_INVALID');

        ret.name = ((await dynamodb.query({
            TableName: visitorTableName,
            IndexName: visitorPhoneNumberIndexName,
            Limit: 1,
            KeyConditionExpression: 'phoneNumber = :phoneNumber',
            ExpressionAttributeValues: { ':phoneNumber': phoneNumber },
        }).promise())?.Items?.[0] as VisitorTableEntry | undefined)?.name;

        ret.status = status;
        return ret;
    }
};

export { handler };

if (module && !module.parent) {
    (async () => {
        console.log(await handler({ "phoneNumber": "+19175391721", "passcode": 999999 }));
        console.log(await handler({ "phoneNumber": "+19175391721", "passcode": 183546 }));
        console.log(await handler({}));
    })();
}
