await (await fetch('https://mcz5ettyj1.execute-api.us-east-1.amazonaws.com/prod1/door', {
    method: 'POST',
    body: JSON.stringify({ status: 'open' }),
})).json();

export const event = { "status": "open" };
