const TJS = require('typescript-json-schema');

const schema = TJS.generateSchema(TJS.getProgramFromFiles(['api.ts']), '*', { ref: false });

for (const [name, definition] of Object.entries(schema.definitions)) {
    console.log(name + '\napplication/json\n' + JSON.stringify(definition, null, 2));
};
