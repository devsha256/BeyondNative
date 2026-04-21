// ========================================================================
// REGRESSION TEST RUNNER - Pre-request Script (Functional)
// This script runs ONLY for the [Regression Test Runner] request
// ========================================================================

// ========================================================================
// Utility Functions
// ========================================================================
const getCollectionVar = (key) => pm.collectionVariables.get(key);

const setCollectionVar = (key, value) => pm.collectionVariables.set(key, value);

const isRegressionMode = () => getCollectionVar("regression_mode") === "true";

const unescapeQuotes = (str) => 
    str.replace(/\\'/g, "'").replace(/\\\\/g, "\\");

const transformMuleUrlToBoomi = (requestUrl, muleBase, boomiBase) => {
    let result = requestUrl.replace(muleBase, boomiBase);
    result = result.replace(/\/[^\/]+\/ws\/rest\//, '/ws/rest/');
    return result;
};

// ========================================================================
// cURL Parsing Functions
// ========================================================================
const URL_PATTERNS = [
    /curl\s+--location\s+'([^']+)'/,      // Pattern 1: curl --location 'URL'
    /curl\s+--location\s+"([^"]+)"/,      // Pattern 2: curl --location "URL"
    /curl\s+'([^']+)'/,                   // Pattern 3: curl 'URL'
    /curl\s+"([^"]+)"/,                   // Pattern 4: curl "URL"
    /curl\s+([^\s-][^\s]*)/               // Pattern 5: curl URL (without quotes)
];

const tryExtractUrl = (curlCommand, pattern) => {
    const match = curlCommand.match(pattern);
    return match && match[1] ? match[1] : null;
};

const extractUrlFromCurl = (curlCommand) => {
    if (!curlCommand || typeof curlCommand !== 'string') return null;
    
    for (const pattern of URL_PATTERNS) {
        const url = tryExtractUrl(curlCommand, pattern);
        if (url) return url;
    }
    
    return null;
};

const extractMethodFromCurl = (curlCommand) => {
    const match = curlCommand.match(/--request\s+(\w+)/);
    return match ? match[1] : 'GET';
};

const extractHeadersFromCurl = (curlCommand) => {
    const headers = {};
    const headerRegex = /--header\s+'([^:]+):\s*([^']+)'/g;
    let match;
    
    while ((match = headerRegex.exec(curlCommand)) !== null) {
        headers[match[1].trim()] = match[2].trim();
    }
    
    return headers;
};

const extractBodyFromCurl = (curlCommand) => {
    const match = curlCommand.match(/--data-raw\s+'([\s\S]*?)'\s*$/);
    return match && match[1] ? unescapeQuotes(match[1]) : null;
};

// ========================================================================
// Request Configuration
// ========================================================================
const parseRequestComponents = (curlCommand) => ({
    url: extractUrlFromCurl(curlCommand),
    method: extractMethodFromCurl(curlCommand),
    headers: extractHeadersFromCurl(curlCommand),
    body: extractBodyFromCurl(curlCommand)
});

const logExtractionResults = (components) => {
    console.log(`Extracted URL: ${components.url}`);
    console.log(`Extracted Method: ${components.method}`);
    console.log(`Extracted Headers: ${Object.keys(components.headers).length}`);
    console.log(`Has Body: ${components.body ? "Yes" : "No"}`);
};

const configureMuleRequest = (components) => {
    pm.request.url = components.url;
    pm.request.method = components.method;
    
    pm.request.headers.clear();
    Object.keys(components.headers).forEach((key) => {
        pm.request.headers.add({
            key: key,
            value: components.headers[key]
        });
    });
    
    if (components.body) {
        pm.request.body = {
            mode: 'raw',
            raw: components.body
        };
    }
    
    console.log(`Mule request configured: ${components.method} ${components.url}`);
};

// ========================================================================
// Authentication Handling
// ========================================================================
const addBasicAuth = (headers) => {
    const username = getCollectionVar("boomi_username");
    const password = getCollectionVar("boomi_password");
    if (username && password) {
        headers['Authorization'] = `Basic ${btoa(`${username}:${password}`)}`;
    }
};

const addBearerAuth = (headers) => {
    const token = getCollectionVar("boomi_bearer_token");
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
};

const addApiKeyAuth = (headers) => {
    const apiKey = getCollectionVar("boomi_api_key");
    const headerName = getCollectionVar("boomi_api_key_header") || "X-API-Key";
    if (apiKey) {
        headers[headerName] = apiKey;
    }
};

const applyAuthentication = (headers, authType) => {
    if (authType === "same") return;
    
    const authHandlers = {
        'basic': () => addBasicAuth(headers),
        'bearer': () => addBearerAuth(headers),
        'api-key': () => addApiKeyAuth(headers)
    };
    
    const handler = authHandlers[authType];
    if (handler) handler();
};

// ========================================================================
// Boomi Request Preparation
// ========================================================================
const getBaseUrls = () => ({
    mule: pm.variables.replaceIn(getCollectionVar("mule_base_url")),
    boomi: pm.variables.replaceIn(getCollectionVar("boomi_base_url"))
});

const validateBaseUrls = (baseUrls) => baseUrls.mule && baseUrls.boomi;

const prepareBoomiHeaders = (extractedHeaders, authType) => {
    const boomiHeaders = { ...extractedHeaders };
    applyAuthentication(boomiHeaders, authType);
    return boomiHeaders;
};

const buildBoomiRequest = (url, method, headers, body) => {
    const boomiRequest = {
        url: url,
        method: method,
        header: headers
    };
    
    if (body) {
        boomiRequest.body = {
            mode: 'raw',
            raw: body
        };
    }
    
    return boomiRequest;
};

// ========================================================================
// Response Handling
// ========================================================================
const handleBoomiError = (err) => {
    console.error("Boomi request failed:", err.message);
    setCollectionVar("boomi_response", `ERROR: ${err.message}`);
    setCollectionVar("boomi_status", 0);
};

const handleBoomiSuccess = (response) => {
    setCollectionVar("boomi_response", response.text());
    setCollectionVar("boomi_status", response.code);
    console.log(`Boomi response received: ${response.code}`);
};

const sendBoomiRequest = (boomiRequest) => {
    console.log("Sending Boomi request...");
    pm.sendRequest(boomiRequest, (err, response) => {
        if (err) {
            handleBoomiError(err);
        } else {
            handleBoomiSuccess(response);
        }
    });
};

// ========================================================================
// Main Workflow
// ========================================================================
const processRegressionTest = (curlCommand, requestName) => {
    console.log(`Processing: ${requestName}`);
    
    const components = parseRequestComponents(curlCommand);
    
    if (!components.url) {
        console.error("Could not extract URL from cURL command");
        console.log(`cURL: ${curlCommand}`);
        return;
    }
    
    logExtractionResults(components);
    configureMuleRequest(components);
    
    const baseUrls = getBaseUrls();
    
    if (!validateBaseUrls(baseUrls)) {
        console.error("Missing base URLs in collection variables");
        return;
    }
    
    const boomiUrl = transformMuleUrlToBoomi(components.url, baseUrls.mule, baseUrls.boomi);
    console.log(`Boomi URL: ${boomiUrl}`);
    
    const authType = getCollectionVar("boomi_auth_type") || "same";
    const boomiHeaders = prepareBoomiHeaders(components.headers, authType);
    const boomiRequest = buildBoomiRequest(boomiUrl, components.method, boomiHeaders, components.body);
    
    setCollectionVar("temp_request_name", requestName);
    setCollectionVar("temp_request_curl", curlCommand);
    
    sendBoomiRequest(boomiRequest);
    
    console.log("=== REGRESSION PRE-REQUEST COMPLETE ===");
    console.log("Mule request will now execute...");
};

// ========================================================================
// Entry Point
// ========================================================================
const runRegressionTestRunner = () => {
    if (!isRegressionMode()) {
        console.log("Not in regression mode, skipping...");
        return;
    }
    
    console.log("=== REGRESSION TEST RUNNER STARTED ===");
    
    const curlCommand = getCollectionVar("regression_curl");
    const requestName = getCollectionVar("regression_request_name");
    
    if (!curlCommand) {
        console.error("No cURL command found from collection pre-request");
        return;
    }
    
    processRegressionTest(curlCommand, requestName);
};

// ========================================================================
// Execute
// ========================================================================
runRegressionTestRunner();
