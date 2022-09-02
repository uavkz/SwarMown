var convert = require('mathml-to-asciimath');

var mathml = '<math><mfrac><mrow><mo>-</mo><mi>b</mi><mo>-</mo><msqrt><msup><mi>b</mi><mn>2</mn></msup><mo>-</mo><mn>4</mn><mi>a</mi><mi>c</mi></msqrt></mrow><mrow><mn>2</mn><mi>a</mi></mrow></mfrac></math>';
// mathml = '<math><mfrac><mrow><mn>1</mn><mo>+</mo><mn>2</mn></mrow><mrow>2</mrow></mfrac></math>';

console.log(convert(mathml)) // => '1 + 2'