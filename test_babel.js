const fs = require('fs');
const babel = require('@babel/core');
try {
    const content = fs.readFileSync('backend/static/login.html', 'utf8');
    const scriptMatch = content.match(/<script type="text\/babel">([\s\S]*?)<\/script>/);
    if (!scriptMatch) {
        console.error('Script not found');
        process.exit(1);
    }
    const script = scriptMatch[1];
    babel.transformSync(script, {presets: ['@babel/preset-react']});
    console.log('BABEL COMPILE SUCCESS');
} catch (e) {
    console.error('BABEL ERROR:', e.message);
}
