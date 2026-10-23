// Lets `node --test extension/test/` work as written: Node loads a folder through its index.js.
"use strict";
require("./payload.test.js");
require("./background.test.js");
