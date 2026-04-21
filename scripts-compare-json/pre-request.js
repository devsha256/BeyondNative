// ========================================================================
// Utility Functions - String & URL Processing
// ========================================================================
const escapeForCurl = (str) => String(str).replace(/'/g, "'\\''");

const escapeBody = (body) => 
    String(body).replace(/\\/g, '\\\\').replace(/'/g, "'\\''");

const transformMuleUrlToBoomi = (requestUrl, muleBase, boomiBase) => {
    const fullUrl = requestUrl;
    let result = fullUrl.replace(muleBase, boomiBase);
    result = result.replace(/\/[^\/]+\/ws\/rest\//, '/ws/rest/');
    return result;
};

// ========================================================================
// Detection & Validation Functions
// ========================================================================
const isCollectionRunner = () => 
    pm.info.iteration !== undefined && pm.info.iteration >= 0;

const hasCurlData = () => 
    pm.iterationData.get("cURL Command");

const isRegressionMode = () => 
    isCollectionRunner() && hasCurlData();

const shouldSkipUtilityRequest = (requestName) => 
    requestName.startsWith("_") || requestName.startsWith("[");

const validateBaseUrls = (muleBaseUrl, boomiBaseUrl) => 
    muleBaseUrl && boomiBaseUrl;

// ========================================================================
// Collection Variable Management
// ========================================================================
const getCollectionVar = (key) => pm.collectionVariables.get(key);

const setCollectionVar = (key, value) => 
    pm.collectionVariables.set(key, value);

const initializeRequestCounter = () => {
    const requestCounter = getCollectionVar("report_request_count");
    if (!requestCounter || requestCounter === "0") {
        setCollectionVar("report_request_count", "0");
    }
};

const incrementRequestCounter = () => {
    const currentCount = parseInt(getCollectionVar("report_request_count") || "0") + 1;
    setCollectionVar("report_request_count", currentCount.toString());
    setCollectionVar("current_report_index", currentCount.toString());
    return currentCount;
};

// ========================================================================
// Regression Mode Handling
// ========================================================================
const handleRegressionMode = () => {
    console.log("=== REGRESSION MODE DETECTED ===");
    
    setCollectionVar("regression_mode", "true");
    setCollectionVar("regression_curl", pm.iterationData.get("cURL Command"));
    setCollectionVar("regression_request_name", pm.iterationData.get("Request Name") || "Unknown");
    
    initializeRequestCounter();
    const currentCount = incrementRequestCounter();
    
    console.log(`Regression test #${currentCount}: ${pm.iterationData.get("Request Name")}`);
    console.log("Variables set. Allowing [Regression Test Runner] to execute...");
};

// ========================================================================
// Header Processing
// ========================================================================
const EXCLUDED_HEADERS = ['host', 'content-length', 'connection', 'user-agent', 'postman-token'];

const shouldIncludeHeader = (header) => 
    !header.disabled && !EXCLUDED_HEADERS.includes(header.key.toLowerCase());

const processHeaders = (currentRequest) => {
    const headers = {};
    currentRequest.headers.each((header) => {
        if (shouldIncludeHeader(header)) {
            const resolvedValue = pm.variables.replaceIn(header.value);
            headers[header.key] = resolvedValue;
        }
    });
    return headers;
};

// ========================================================================
// Body Processing
// ========================================================================
const BODY_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE'];

const shouldProcessBody = (method) => BODY_METHODS.includes(method);

const processFormData = (formDataCollection) => {
    const formData = {};
    formDataCollection.each((item) => {
        if (!item.disabled) {
            formData[item.key] = pm.variables.replaceIn(item.value);
        }
    });
    return formData;
};

const processUrlEncoded = (urlencodedCollection) => {
    const urlencodedData = {};
    urlencodedCollection.each((item) => {
        if (!item.disabled) {
            urlencodedData[item.key] = pm.variables.replaceIn(item.value);
        }
    });
    return urlencodedData;
};

const processGraphQL = (graphqlBody) => 
    JSON.stringify({
        query: pm.variables.replaceIn(graphqlBody.query),
        variables: graphqlBody.variables
    });

const processRequestBody = (currentRequest, method) => {
    if (!currentRequest.body || !shouldProcessBody(method)) {
        return { requestBody: null, bodyMode: null };
    }
    
    const bodyMode = currentRequest.body.mode;
    let requestBody = null;
    
    switch (bodyMode) {
        case 'raw':
            requestBody = pm.variables.replaceIn(currentRequest.body.raw);
            break;
        case 'formdata':
            requestBody = processFormData(currentRequest.body.formdata);
            break;
        case 'urlencoded':
            requestBody = processUrlEncoded(currentRequest.body.urlencoded);
            break;
        case 'graphql':
            requestBody = processGraphQL(currentRequest.body.graphql);
            break;
    }
    
    return { requestBody, bodyMode };
};

// ========================================================================
// Content Type Detection
// ========================================================================
const detectContentType = (trimmedBody) => {
    if (trimmedBody.startsWith('{') || trimmedBody.startsWith('[')) {
        return 'application/json';
    } else if (trimmedBody.startsWith('<')) {
        return 'application/xml';
    }
    return null;
};

const addContentTypeIfNeeded = (headers, requestBody, bodyMode, method) => {
    if (!requestBody || method === 'GET') return;
    
    const existingContentType = headers['Content-Type'] || headers['content-type'];
    if (!existingContentType && bodyMode === 'raw') {
        const trimmedBody = requestBody.trim();
        const contentType = detectContentType(trimmedBody);
        if (contentType) {
            headers['Content-Type'] = contentType;
        }
    }
};

// ========================================================================
// Authentication Handling
// ========================================================================
const addBasicAuth = (headers) => {
    const boomiUsername = getCollectionVar("boomi_username");
    const boomiPassword = getCollectionVar("boomi_password");
    if (boomiUsername && boomiPassword) {
        headers['Authorization'] = `Basic ${btoa(`${boomiUsername}:${boomiPassword}`)}`;
    }
};

const addBearerAuth = (headers) => {
    const boomiToken = getCollectionVar("boomi_bearer_token");
    if (boomiToken) {
        headers['Authorization'] = `Bearer ${boomiToken}`;
    }
};

const addApiKeyAuth = (headers) => {
    const boomiApiKey = getCollectionVar("boomi_api_key");
    const boomiApiKeyHeader = getCollectionVar("boomi_api_key_header") || "X-API-Key";
    if (boomiApiKey) {
        headers[boomiApiKeyHeader] = boomiApiKey;
    }
};

const applyAuthentication = (headers) => {
    const authType = getCollectionVar("boomi_auth_type") || "same";
    
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
// Request Building
// ========================================================================
const buildBoomiRequestBody = (requestBody, bodyMode) => {
    if (!requestBody) return null;
    
    const bodyModes = {
        'raw': { mode: 'raw', raw: requestBody },
        'formdata': { mode: 'formdata', formdata: requestBody },
        'urlencoded': { mode: 'urlencoded', urlencoded: requestBody }
    };
    
    return bodyModes[bodyMode] || {
        mode: 'raw',
        raw: typeof requestBody === 'string' ? requestBody : JSON.stringify(requestBody)
    };
};

const buildBoomiRequest = (boomiUrl, method, headers, requestBody, bodyMode) => {
    const boomiRequest = {
        url: boomiUrl,
        method: method,
        header: headers
    };
    
    const body = buildBoomiRequestBody(requestBody, bodyMode);
    if (body) {
        boomiRequest.body = body;
    }
    
    return boomiRequest;
};

// ========================================================================
// cURL Command Generation - CORRECTED ESCAPING
// ========================================================================
const escapeForCurl = (str) => {
    // For cURL shell commands, single quotes need special handling
    // Replace ' with '\'' (end quote, escaped quote, start quote)
    return String(str).replace(/'/g, "'\\''");
};

const escapeBody = (body) => {
    // Body needs both backslash and single quote escaping
    return String(body).replace(/\\/g, '\\\\').replace(/'/g, "'\\''");
};

const buildCurlBase = (requestUrl, method) => {
    const escapedUrl = escapeForCurl(requestUrl);
    let curlCommand = `curl --location '${escapedUrl}'`;
    if (method !== 'GET') {
        curlCommand += ` \\\n--request ${method}`;
    }
    return curlCommand;
};

const addCurlHeaders = (curlCommand, headers) => {
    if (!headers || typeof headers !== 'object') return curlCommand;
    
    Object.entries(headers).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
            const escapedValue = escapeForCurl(value);
            curlCommand += ` \\\n--header '${key}: ${escapedValue}'`;
        }
    });
    
    return curlCommand;
};

const addCurlBody = (curlCommand, requestBody, bodyMode) => {
    if (!requestBody || requestBody.trim() === '') return curlCommand;
    
    const escapedBody = escapeBody(requestBody);
    curlCommand += ` \\\n--data-raw '${escapedBody}'`;
    return curlCommand;
};

const generateCurlCommand = (requestUrl, method, headers, requestBody, bodyMode) => {
    let curlCommand = buildCurlBase(requestUrl, method);
    curlCommand = addCurlHeaders(curlCommand, headers);
    curlCommand = addCurlBody(curlCommand, requestBody, bodyMode);
    return curlCommand;
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
const processNormalRequest = () => {
    initializeRequestCounter();
    const currentCount = incrementRequestCounter();
    console.log(`Processing request #${currentCount}: ${pm.info.requestName}`);
    
    const muleBaseUrl = pm.variables.replaceIn(getCollectionVar("mule_base_url"));
    const boomiBaseUrl = pm.variables.replaceIn(getCollectionVar("boomi_base_url"));
    
    if (!validateBaseUrls(muleBaseUrl, boomiBaseUrl)) {
        console.error("Missing base URLs in collection variables");
        return;
    }
    
    const currentRequest = pm.request;
    const method = currentRequest.method;
    const requestUrl = pm.variables.replaceIn(pm.request.url.toString());
    
    const boomiUrl = transformMuleUrlToBoomi(requestUrl, muleBaseUrl, boomiBaseUrl);
    
    console.log(`Mule URL: ${requestUrl}`);
    console.log(`Boomi URL: ${boomiUrl}`);
    
    if (!boomiUrl) {
        console.error("Failed to generate Boomi URL");
        return;
    }
    
    const headers = processHeaders(currentRequest);
    const { requestBody, bodyMode } = processRequestBody(currentRequest, method);
    
    addContentTypeIfNeeded(headers, requestBody, bodyMode, method);
    applyAuthentication(headers);
    
    const boomiRequest = buildBoomiRequest(boomiUrl, method, headers, requestBody, bodyMode);
    const curlCommand = generateCurlCommand(requestUrl, method, headers, requestBody, bodyMode);
    
    setCollectionVar("temp_request_name", pm.info.requestName);
    setCollectionVar("temp_request_curl", curlCommand);
    console.log(`cURL generated successfully, length: ${curlCommand.length} characters`);
    
    sendBoomiRequest(boomiRequest);
};

// ========================================================================
// Entry Point
// ========================================================================
if (isRegressionMode()) {
    handleRegressionMode();
    return;
}

setCollectionVar("regression_mode", "false");

if (shouldSkipUtilityRequest(pm.info.requestName)) {
    console.log(`Skipping pre-request for: ${pm.info.requestName}`);
    return;
}

processNormalRequest();
