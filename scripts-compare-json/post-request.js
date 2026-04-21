// ========================================================================
// Utility: Primitives, JSON, Regex
// ========================================================================
const isPrimitive = (value) => typeof value !== 'object' || value === null;

const parseJSON = (text) => {
    try { return JSON.parse(text); }
    catch (e) { return text; }
};

// ========================================================================
// Field Exemption with Full Regex and Wildcard Support
// ========================================================================
const escapeRegex = (str) => str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const isWildcardPattern = (field) => field.includes('*') || field.includes('?');

const isFullRegexPattern = (field) => 
    field.startsWith('/') && field.lastIndexOf('/') > 0;

const convertWildcardToRegex = (pattern) => {
    let regexPattern = pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&');
    regexPattern = regexPattern.replace(/\*/g, '.*');
    regexPattern = regexPattern.replace(/\?/g, '.');
    return regexPattern;
};

const parseFullRegex = (regexString) => {
    const lastSlashIndex = regexString.lastIndexOf('/');
    const pattern = regexString.slice(1, lastSlashIndex);
    const flags = regexString.slice(lastSlashIndex + 1);
    
    try {
        return new RegExp(pattern, flags);
    } catch (e) {
        console.warn(`Invalid regex pattern: ${regexString}`, e.message);
        return null;
    }
};

const extractFieldName = (path) => {
    if (!path) return '';
    // Extract the last field name from path like "data.user.name" -> "name"
    // or "items[0].status" -> "status"
    const match = path.match(/\.([^.\[\]]+)$|^([^.\[\]]+)$/);
    return match ? (match[1] || match[2]) : path;
};

const isFieldExempted = (path, exemptedField) => {
    if (!path || !exemptedField) return { isExempted: false, matchedField: null };
    
    // Mode 1: Full Regex Pattern (wrapped in slashes)
    if (isFullRegexPattern(exemptedField)) {
        const regex = parseFullRegex(exemptedField);
        if (regex && regex.test(path)) {
            return { isExempted: true, matchedField: path };
        }
        return { isExempted: false, matchedField: null };
    }
    
    // Mode 2: Wildcard Pattern (contains * or ?)
    if (isWildcardPattern(exemptedField)) {
        const fieldName = extractFieldName(path);
        const regexPattern = convertWildcardToRegex(exemptedField);
        const pattern = new RegExp(`^${regexPattern}$`);
        
        if (pattern.test(fieldName)) {
            return { isExempted: true, matchedField: path };
        }
        return { isExempted: false, matchedField: null };
    }
    
    // Mode 3: Simple String (exact field name match)
    const fieldName = extractFieldName(path);
    if (fieldName === exemptedField) {
        return { isExempted: true, matchedField: path };
    }
    
    return { isExempted: false, matchedField: null };
};


// ========================================================================
// Data Normalization
// ========================================================================
const normalizeValue = (value) => {
    if (Array.isArray(value)) {
        const allPrimitive = value.every(isPrimitive);
        return allPrimitive ? [...value].sort() : value.map(normalizeValue);
    }
    if (value !== null && typeof value === 'object') {
        return Object.keys(value)
            .sort()
            .reduce((acc, key) => ({
                ...acc,
                [key]: normalizeValue(value[key])
            }), {});
    }
    return value;
};

// ========================================================================
// JSON Line Construction
// ========================================================================
const createLine = (text, indent, path, additionalProps = {}) => ({
    text,
    indent,
    path,
    ...additionalProps
});

const buildJSONLinesRecursive = (obj, path = '', indent = 0) => {
    if (obj === null)
        return [createLine('null', indent, path, { isPrimitive: true })];
    if (!isPrimitive(obj)) {
        if (Array.isArray(obj))
            return buildArrayLines(obj, path, indent);
        return buildObjectLines(obj, path, indent);
    }
    return [createLine(JSON.stringify(obj), indent, path, { isPrimitive: true, value: obj })];
};

const buildArrayLines = (arr, path, indent) => {
    const allPrimitive = arr.every(isPrimitive);
    const lines = [createLine('[', indent, path, { type: 'open-array' })];
    arr.forEach((item, idx) => {
        const itemPath = `${path}[${idx}]`;
        const comma = idx < arr.length - 1 ? ',' : '';
        const itemLines = buildJSONLinesRecursive(item, itemPath, indent + 1);
        itemLines.forEach((line, lineIdx) => {
            if (lineIdx === itemLines.length - 1) line.text += comma;
            if (allPrimitive && line.isPrimitive) {
                line.arrayPath = path;
                line.arrayValue = item;
            }
            lines.push(line);
        });
    });
    lines.push(createLine(']', indent, path, { type: 'close-array' }));
    return lines;
};

const buildObjectLines = (obj, path, indent) => {
    const lines = [createLine('{', indent, path, { type: 'open-object' })];
    const keys = Object.keys(obj).sort();
    keys.forEach((key, idx) => {
        const keyPath = path ? `${path}.${key}` : key;
        const value = obj[key];
        const comma = idx < keys.length - 1 ? ',' : '';
        if (!isPrimitive(value)) {
            lines.push(createLine(`"${key}": `, indent + 1, keyPath, { type: 'key' }));
            const valueLines = buildJSONLinesRecursive(value, keyPath, indent + 1);
            valueLines.forEach((line, lineIdx) => {
                if (lineIdx === valueLines.length - 1) line.text += comma;
                lines.push(line);
            });
        } else {
            lines.push(createLine(`"${key}": ${JSON.stringify(value)}${comma}`, indent + 1, keyPath, { isPrimitive: true, value }));
        }
    });
    lines.push(createLine('}', indent, path, { type: 'close-object' }));
    return lines;
};

const buildJSONLines = (normalizedData) => ({
    boomiLines: buildJSONLinesRecursive(normalizedData.boomiNorm),
    muleLines: buildJSONLinesRecursive(normalizedData.muleNorm)
});

// ========================================================================
// Array Alignment (LCS)
// ========================================================================
const groupArrayElements = (lines, sourceType) => {
    return lines.reduce((groups, line, idx) => {
        if (line.arrayPath) {
            if (!groups[line.arrayPath]) groups[line.arrayPath] = { boomi: [], mule: [] };
            groups[line.arrayPath][sourceType].push({ line, idx });
        }
        return groups;
    }, {});
};

const findValueInRange = (value, array, startIdx, range = 10) => {
    const endIdx = Math.min(startIdx + range, array.length);
    for (let i = startIdx + 1; i < endIdx; i++) {
        if (value === array[i]) return i;
    }
    return -1;
};

const alignArrayPair = (bValues, mValues) => {
    const aligned = [];
    let bIdx = 0;
    let mIdx = 0;
    while (bIdx < bValues.length || mIdx < mValues.length) {
        if (bIdx >= bValues.length) aligned.push({ bIdx: null, mIdx: mIdx++ });
        else if (mIdx >= mValues.length) aligned.push({ bIdx: bIdx++, mIdx: null });
        else if (bValues[bIdx] === mValues[mIdx]) aligned.push({ bIdx: bIdx++, mIdx: mIdx++ });
        else {
            const foundInMule = findValueInRange(bValues[bIdx], mValues, mIdx);
            const foundInBoomi = findValueInRange(mValues[mIdx], bValues, bIdx);
            if (foundInMule === -1 && foundInBoomi === -1) {
                aligned.push({ bIdx: bIdx++, mIdx: null });
                aligned.push({ bIdx: null, mIdx: mIdx++ });
            } else if (foundInMule !== -1 && (foundInBoomi === -1 || (foundInMule - mIdx) <= (foundInBoomi - bIdx))) {
                aligned.push({ bIdx: null, mIdx: mIdx++ });
            } else {
                aligned.push({ bIdx: bIdx++, mIdx: null });
            }
        }
    }
    return aligned;
};

const createAlignmentMap = (bItems, mItems, aligned) => {
    const alignmentMap = { boomi: new Map(), mule: new Map() };
    aligned.forEach(pair => {
        if (pair.bIdx !== null && pair.mIdx !== null) {
            alignmentMap.boomi.set(bItems[pair.bIdx].idx, mItems[pair.mIdx].idx);
            alignmentMap.mule.set(mItems[pair.mIdx].idx, bItems[pair.bIdx].idx);
        }
    });
    return alignmentMap;
};

const alignPrimitiveArrays = (bLines, mLines) => {
    const bGroups = groupArrayElements(bLines, 'boomi');
    const mGroups = groupArrayElements(mLines, 'mule');
    const arrayGroups = { ...bGroups };
    Object.keys(mGroups).forEach(key => {
        if (!arrayGroups[key]) arrayGroups[key] = { boomi: [], mule: [] };
        arrayGroups[key].mule = mGroups[key].mule;
    });
    const combinedMap = { boomi: new Map(), mule: new Map() };
    Object.keys(arrayGroups).forEach(arrayPath => {
        const { boomi: bItems, mule: mItems } = arrayGroups[arrayPath];
        const bValues = bItems.map(item => item.line.arrayValue);
        const mValues = mItems.map(item => item.line.arrayValue);
        const aligned = alignArrayPair(bValues, mValues);
        const alignmentMap = createAlignmentMap(bItems, mItems, aligned);
        alignmentMap.boomi.forEach((v, k) => combinedMap.boomi.set(k, v));
        alignmentMap.mule.forEach((v, k) => combinedMap.mule.set(k, v));
    });
    return combinedMap;
};

// ========================================================================
// Line Alignment & Visualization Helpers
// ========================================================================
const createEmptyLine = (referenceLine) => ({
    text: '',
    indent: referenceLine.indent,
    isEmpty: true,
    path: referenceLine.path
});

const createAlignedPair = (boomi, mule, status) => ({ boomi, mule, status });

const determineAlignmentStatus = (leftLine, rightLine) => {
    if (leftLine.path === rightLine.path && leftLine.type === rightLine.type) {
        return (leftLine.text !== rightLine.text && !leftLine.type) ? 'mismatch' : 'match';
    }
    return null;
};

const lookAhead = (lines, startIdx, targetPath, targetType, range = 30) => {
    const endIdx = Math.min(startIdx + range, lines.length);
    for (let i = startIdx + 1; i < endIdx; i++) {
        if (lines[i].path === targetPath && lines[i].type === targetType) return true;
    }
    return false;
};

const alignLinesWithArrays = (leftLines, rightLines, arrayMap) => {
    const aligned = [];
    let leftIdx = 0, rightIdx = 0;
    while (leftIdx < leftLines.length || rightIdx < rightLines.length) {
        const leftLine = leftLines[leftIdx];
        const rightLine = rightLines[rightIdx];

        if (!leftLine) {
            aligned.push(createAlignedPair(createEmptyLine(rightLine), rightLine, 'only_mule'));
            rightIdx++;
        } else if (!rightLine) {
            aligned.push(createAlignedPair(leftLine, createEmptyLine(leftLine), 'only_boomi'));
            leftIdx++;
        } else {
            const mappedRight = arrayMap.boomi.get(leftIdx);
            const mappedLeft = arrayMap.mule.get(rightIdx);

            if (mappedRight === rightIdx) {
                aligned.push(createAlignedPair(leftLine, rightLine, 'match'));
                leftIdx++; rightIdx++;
            } else if (leftLine.arrayPath && !mappedRight) {
                aligned.push(createAlignedPair(leftLine, createEmptyLine(leftLine), 'only_boomi'));
                leftIdx++;
            } else if (rightLine.arrayPath && !mappedLeft) {
                aligned.push(createAlignedPair(createEmptyLine(rightLine), rightLine, 'only_mule'));
                rightIdx++;
            } else {
                const status = determineAlignmentStatus(leftLine, rightLine);

                if (status) {
                    aligned.push(createAlignedPair(leftLine, rightLine, status));
                    leftIdx++; rightIdx++;
                } else {
                    const rightHasPath = lookAhead(rightLines, rightIdx, leftLine.path, leftLine.type);
                    const leftHasPath = lookAhead(leftLines, leftIdx, rightLine.path, rightLine.type);

                    if (!rightHasPath) {
                        aligned.push(createAlignedPair(leftLine, createEmptyLine(leftLine), 'only_boomi'));
                        leftIdx++;
                    } else if (!leftHasPath) {
                        aligned.push(createAlignedPair(createEmptyLine(rightLine), rightLine, 'only_mule'));
                        rightIdx++;
                    } else {
                        if (leftLine.path < rightLine.path) {
                            aligned.push(createAlignedPair(leftLine, createEmptyLine(leftLine), 'only_boomi'));
                            leftIdx++;
                        } else {
                            aligned.push(createAlignedPair(createEmptyLine(rightLine), rightLine, 'only_mule'));
                            rightIdx++;
                        }
                    }
                }
            }
        }
    }
    return aligned;
};

const alignLines = (lines) => {
    const arrayAlignment = alignPrimitiveArrays(lines.boomiLines, lines.muleLines);
    return alignLinesWithArrays(lines.boomiLines, lines.muleLines, arrayAlignment);
};

// ========================================================================
// Statistics Calculation (Updated)
// ========================================================================
const initializeStats = () => ({
    totalMismatches: 0,
    totalExempted: 0,
    totalMatched: 0,
    totalOnlyMule: 0,
    exemptedFieldsFound: []
});

const checkExemption = (path, exemptedFields) => {
    for (const field of exemptedFields) {
        const result = isFieldExempted(path, field);
        if (result.isExempted) {
            return { isExempted: true, matchedField: result.matchedField };
        }
    }
    return { isExempted: false, matchedField: null };
};

const updateStats = (stats, status, isExempted, matchedField) => {
    if (isExempted) {
        stats.totalExempted++;
        // Log the actual field path, not the pattern
        if (!stats.exemptedFieldsFound.includes(matchedField)) {
            stats.exemptedFieldsFound.push(matchedField);
        }
    } else {
        switch (status) {
            case 'match':
                stats.totalMatched++;
                break;
            case 'mismatch':
            case 'only_boomi':
                stats.totalMismatches++;
                break;
            case 'only_mule':
                stats.totalOnlyMule++;
                break;
        }
    }
};

const calculateStats = (aligned, exemptedFields) => {
    const stats = initializeStats();
    
    aligned.forEach(pair => {
        const path = pair.boomi.path || pair.mule.path;
        const { isExempted, matchedField } = checkExemption(path, exemptedFields);
        
        if (isExempted) {
            pair.status = 'exempted';
        }
        
        updateStats(stats, pair.status, isExempted, matchedField);
    });
    
    const exemptedFieldsList = stats.exemptedFieldsFound.join(', ');
    const totalComparedLines = stats.totalMatched + stats.totalMismatches + stats.totalExempted;
    const matchPercentage = totalComparedLines > 0 
        ? Math.round((stats.totalMatched / totalComparedLines) * 10000) / 100 
        : 0;
    const statusText = stats.totalMismatches === 0 ? "PASSED" : "FAILED";
    
    return {
        ...stats,
        totalLines: aligned.length,
        exemptedFieldsList,
        matchPercentage,
        statusText
    };
};

const runTests = (stats, context) => {
    pm.test("Boomi API responded", () =>
        pm.expect(context.boomiStatus).to.be.oneOf([200, 201, 202, 204])
    );
    pm.test("MuleSoft API responded", () =>
        pm.expect(pm.response.code).to.be.oneOf([200, 201, 202, 204])
    );
    pm.test("Boomi & Mule Status code match", () =>
        pm.expect(context.boomiStatus).to.equal(pm.response.code)
    );
    pm.test("All non-exempted fields match", () =>
        pm.expect(stats.totalMismatches).to.equal(0)
    );
};

const logStatistics = (stats) => {
    console.log("=== COMPARISON BREAKDOWN ===");
    console.log(`Exempted fields: ${stats.exemptedFieldsList || "None"}`);
    console.log(`Total matched: ${stats.totalMatched}`);
    console.log(`Total mismatches: ${stats.totalMismatches} (includes only_boomi)`);
    console.log(`Total exempted: ${stats.totalExempted}`);
    console.log(`Only in Mule (ignored): ${stats.totalOnlyMule}`);
    console.log("=== STATISTICS ===");
    console.log(`Total aligned lines: ${stats.totalLines}`);
    console.log(`Match percentage: ${stats.matchPercentage}%`);
    console.log(`Overall status: ${stats.statusText}`);
};

// ========================================================================
// Report Storage - CORRECTED MULTI-LAYER ESCAPING
// ========================================================================
const minifyResponse = (text) => {
    if (!text) return "";
    
    try {
        // Remove all newlines and extra whitespace from XML/JSON
        const cleaned = text.replace(/\r?\n|\r/g, ' ').replace(/\s+/g, ' ').trim();
        // NO escaping here - will be done during CSV generation
        return cleaned;
    } catch (e) {
        return text.replace(/\r?\n|\r/g, ' ').replace(/\s+/g, ' ').trim();
    }
};

const cleanCurlCommand = (curlCommand) => {
    // Remove newlines and extra spaces from cURL for storage
    // DO NOT escape here - the cURL already has shell escaping
    // CSV escaping will be done during CSV generation
    return curlCommand.replace(/\\\n/g, ' ')  // Remove line continuations
                      .replace(/\s+/g, ' ')    // Collapse multiple spaces
                      .trim();
};

const createStatsObject = (stats, context) => ({
    totalLines: stats.totalLines,
    matchedLines: stats.totalMatched,
    mismatchedLines: stats.totalMismatches,
    exemptedLines: stats.totalExempted,
    exemptedFields: stats.exemptedFieldsList,
    matchPercentage: stats.matchPercentage,
    status: stats.statusText,
    boomiStatus: context.boomiStatus,
    mulesoftStatus: pm.response.code,
    timestamp: new Date().toISOString()
});

const createReportEntry = (context, stats) => ({
    serialNumber: parseInt(context.reportIndex),
    requestName: context.requestName,
    curlCommand: cleanCurlCommand(context.curlCommand),  // Clean but don't escape
    boomiResponse: context.skipPayloadLogging 
        ? "[PAYLOAD_SKIPPED]" 
        : minifyResponse(context.boomiResponseRaw),
    mulesoftResponse: context.skipPayloadLogging 
        ? "[PAYLOAD_SKIPPED]" 
        : minifyResponse(context.mulesoftResponseRaw),
    statistics: createStatsObject(stats, context)
});

const storeReport = (context, stats) => {
    const reportEntry = createReportEntry(context, stats);
    const paddedIndex = context.reportIndex.padStart(3, '0');
    
    // JSON.stringify will handle the JSON escaping
    pm.collectionVariables.set(`report_data_${paddedIndex}`, JSON.stringify(reportEntry));
    console.log(`Report stored with cURL length: ${context.curlCommand.length}`);
    
    pm.collectionVariables.set("temp_request_name", "");
    pm.collectionVariables.set("temp_request_curl", "");
};


const createTableRow = (pair) => {
    const { boomi: bLine, mule: mLine, status } = pair;

    // Align with Material Design's 8dp grid system for consistent spacing.
    // The base padding is 16px, and each indentation level adds another 16px.
    const basePadding = 16; // Corresponds to --spacing-medium in CSS
    const indentStep = 16;  // Additional space for each level of nesting

    const bIndent = basePadding + (bLine.indent * indentStep);
    const mIndent = basePadding + (mLine.indent * indentStep);

    const bText = bLine.isEmpty ? '' : bLine.text;
    const mText = mLine.isEmpty ? '' : mLine.text;

    // Map status to a visual pointer for quick identification of differences.
    const pointerMap = { 'mismatch': '↔', 'only_boomi': '→', 'only_mule': '←' };
    const pointer = pointerMap[status] || '';

    // Use a non-breaking space for empty lines to maintain table row height and structure.
    const emptySpan = '<span class="empty">&nbsp;</span>';
    
    // The class on the <tr> is used by the stylesheet to apply a status-colored left border.
    // This provides a subtle, scannable indicator without overwhelming the user with row colors.
    // A fallback to 'match' is added for pairs without a special status.
    return `<tr class="${status || 'match'}">
        <td style="padding-left: ${bIndent}px">${bText || emptySpan}</td>
        <td class="pointer">${pointer}</td>
        <td style="padding-left: ${mIndent}px">${mText || emptySpan}</td>
    </tr>`;
};


const generateVisualizerHTML = (aligned, stats, requestName) => {
    const tableRows = aligned.map(createTableRow).join('');
    const statusColor = stats.totalMismatches > 0 ? 'var(--md-sys-color-error-container)' : 'var(--md-sys-color-primary-container)';
    const statusTextColor = stats.totalMismatches > 0 ? 'var(--md-sys-color-on-error-container)' : 'var(--md-sys-color-on-primary-container)';

    return `
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
        <style>
            :root {
                --md-sys-color-primary: #6750A4;
                --md-sys-color-on-primary: #FFFFFF;
                --md-sys-color-primary-container: #EADDFF;
                --md-sys-color-on-primary-container: #21005D;
                --md-sys-color-surface: #FFFBFE;
                --md-sys-color-surface-variant: #E7E0EC;
                --md-sys-color-on-surface: #1C1B1F;
                --md-sys-color-on-surface-variant: #49454F;
                --md-sys-color-outline: #79747E;
                --md-sys-color-error: #B3261E;
                --md-sys-color-error-container: #F9DEDC;
                --md-sys-color-on-error-container: #410E0B;

                --status-mismatch: #B3261E;
                --status-exempted: #79747E;
                --status-only-boomi: #6750A4;
                --status-only-mule: #0061A4;
                
                --border-radius: 16px;
                --spacing-small: 8px;
                --spacing-medium: 16px;
                --spacing-large: 24px;
            }

            body {
                margin: 0;
                padding: var(--spacing-large);
                box-sizing: border-box;
                font-family: 'Roboto', 'Arial', sans-serif;
                font-size: 14px;
                background-color: #F7F2FA;
                color: var(--md-sys-color-on-surface);
            }

            .main-container {
                display: flex;
                flex-direction: column;
                gap: var(--spacing-large);
            }

            .card {
                background-color: var(--md-sys-color-surface);
                border-radius: var(--border-radius);
                padding: var(--spacing-medium);
                box-shadow: 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06);
                overflow: hidden;
            }
            
            .header-card {
                padding: 0;
            }

            .header-title {
                padding: var(--spacing-medium);
            }

            .header-title h2 {
                font-size: 22px;
                font-weight: 500;
                margin: 0;
                color: var(--md-sys-color-on-surface);
            }
            
            .header-stats-container {
                display: flex;
                justify-content: space-between;
                align-items: center;
                border-top: 1px solid var(--md-sys-color-surface-variant);
                padding: var(--spacing-medium);
                flex-wrap: wrap;
                gap: var(--spacing-medium);
            }

            .stats-group {
                display: flex;
                gap: var(--spacing-large);
                flex-wrap: wrap;
            }
            
            .stat-item {
                display: flex;
                flex-direction: column;
            }

            .stat-item .label {
                font-size: 12px;
                color: var(--md-sys-color-on-surface-variant);
            }

            .stat-item .value {
                font-size: 18px;
                font-weight: 500;
            }
            
            .status-badge {
                padding: var(--spacing-small) var(--spacing-medium);
                border-radius: 8px;
                font-weight: 500;
                background-color: ${statusColor};
                color: ${statusTextColor};
            }

            .legend-card {
                display: flex;
                align-items: center;
                gap: var(--spacing-large);
                font-size: 12px;
                flex-wrap: wrap;
            }
            
            .legend-title {
                font-weight: 700;
                color: var(--md-sys-color-on-surface-variant);
            }

            .legend-item {
                display: flex;
                align-items: center;
                gap: var(--spacing-small);
            }

            .legend-box {
                width: 14px;
                height: 14px;
                border-radius: 4px;
                border: 2px solid;
            }

            .legend-box.match { border-color: transparent; }
            .legend-box.mismatch { border-color: var(--status-mismatch); }
            .legend-box.exempted { border-color: var(--status-exempted); }
            .legend-box.onlyboomi { border-color: var(--status-only-boomi); }
            .legend-box.onlymule { border-color: var(--status-only-mule); }

            .table-container {
                max-height: 70vh;
                overflow: auto;
                border: 1px solid var(--md-sys-color-surface-variant);
                border-radius: var(--border-radius);
            }

            table {
                width: 100%;
                border-collapse: collapse;
                font-size: 12px;
                table-layout: fixed;
            }

            thead {
                position: sticky;
                top: 0;
                background: var(--md-sys-color-surface);
                z-index: 10;
            }

            th {
                padding: var(--spacing-medium);
                text-align: left;
                font-weight: 700;
                font-size: 12px;
                color: var(--md-sys-color-on-surface-variant);
                border-bottom: 1px solid var(--md-sys-color-outline);
            }
            
            th:first-child { width: 47%; }
            th:nth-child(2) { width: 6%; text-align: center; }
            th:last-child { width: 47%; }

            tbody tr {
                transition: background-color 0.15s ease-in-out;
                border-left: 4px solid transparent;
            }
            
            tbody tr:hover {
                background-color: var(--md-sys-color-primary-container);
            }
            
            tbody tr.mismatch { border-left-color: var(--status-mismatch); }
            tbody tr.exempted { border-left-color: var(--status-exempted); }
            tbody tr.onlyboomi { border-left-color: var(--status-only-boomi); }
            tbody tr.onlymule { border-left-color: var(--status-only-mule); }

            td {
                padding: var(--spacing-small) var(--spacing-medium);
                border-bottom: 1px solid var(--md-sys-color-surface-variant);
                font-family: 'Consolas', 'Monaco', monospace;
                vertical-align: top;
                word-wrap: break-word;
                white-space: pre-wrap;
                line-height: 1.5;
            }

            td.pointer {
                text-align: center;
                font-family: 'Roboto', sans-serif;
                font-size: 18px;
                vertical-align: middle;
                color: var(--status-mismatch);
            }

            .empty { color: #BDBDBD; }

            .signature {
                text-align: right;
                margin-top: var(--spacing-medium);
                font-size: 10px;
                color: var(--md-sys-color-on-surface-variant);
                font-style: italic;
            }

        </style>
    </head>
    <body>
        <div class="main-container">
            <div class="card header-card">
                <div class="header-title">
                    <h2>Response Comparison: ${requestName}</h2>
                </div>
                <div class="header-stats-container">
                    <div class="stats-group">
                        <div class="stat-item"><span class="label">Lines</span><span class="value">${stats.totalLines}</span></div>
                        <div class="stat-item"><span class="label">Mismatched</span><span class="value">${stats.totalMismatches}</span></div>
                        <div class="stat-item"><span class="label">Exempted</span><span class="value">${stats.totalExempted}</span></div>
                        <div class="stat-item"><span class="label">Match %</span><span class="value">${stats.matchPercentage}%</span></div>
                    </div>
                    <div class="status-badge">${stats.statusText}</div>
                </div>
            </div>

            <div class="card legend-card">
                <span class="legend-title">Legend:</span>
                <div class="legend-item"><div class="legend-box match"></div><span>Match</span></div>
                <div class="legend-item"><div class="legend-box mismatch"></div><span>Mismatch</span></div>
                <div class="legend-item"><div class="legend-box exempted"></div><span>Exempted</span></div>
                <div class="legend-item"><div class="legend-box onlyboomi"></div><span>Only Boomi</span></div>
                <div class="legend-item"><div class="legend-box onlymule"></div><span>Only Mule</span></div>
            </div>

            <div class="card table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Boomi JSON</th>
                            <th></th>
                            <th>MuleSoft JSON</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${tableRows}
                    </tbody>
                </table>
            </div>
        </div>
        <div class="signature">S. 2025</div>
    </body>
    </html>
    `;
};


const renderVisualizer = (aligned, stats, requestName) => {
    console.log("Rendering side-by-side JSON visualizer");
    const html = generateVisualizerHTML(aligned, stats, requestName);
    pm.visualizer.set(html);
    console.log("Visualizer rendered with LCS array alignment");
};

// ========================================================================
// Context and Main Workflow: Must be Last for Hoisting
// ========================================================================
const getRegressionMode = () => pm.collectionVariables.get("regression_mode");

const shouldSkipRequest = (requestName, regressionMode) =>
    requestName.startsWith("[") && regressionMode !== "true";

const logRegression = (regressionMode) => {
    if (regressionMode === "true") {
        console.log("=== REGRESSION POST-REQUEST: Processing comparison ===");
    }
};

const buildComparisonContext = () => ({
    boomiResponseRaw: pm.collectionVariables.get("boomi_response"),
    boomiStatus: pm.collectionVariables.get("boomi_status"),
    mulesoftResponseRaw: pm.response.text(),
    reportIndex: pm.collectionVariables.get("current_report_index"),
    requestName: pm.collectionVariables.get("temp_request_name") || pm.info.requestName,
    curlCommand: pm.collectionVariables.get("temp_request_curl") || "",
    skipPayloadLogging: pm.collectionVariables.get("skip_payload_logging") === "true",
    exemptedFields: (() => {
        const exemptedFieldsStr = pm.collectionVariables.get("exempted_fields");
        return exemptedFieldsStr ? JSON.parse(exemptedFieldsStr) : [];
    })()
});

const validateContext = (context) =>
    context.boomiResponseRaw &&
    context.boomiResponseRaw !== "" &&
    !context.boomiResponseRaw.startsWith("ERROR:");

function executeComparison() {
    const context = buildComparisonContext();

    if (!validateContext(context)) {
        console.error("Boomi response invalid");
        return;
    }
    const parsedData = {
        boomi: parseJSON(context.boomiResponseRaw),
        mule: parseJSON(context.mulesoftResponseRaw)
    };
    const normalizedData = {
        boomiNorm: normalizeValue(parsedData.boomi),
        muleNorm: normalizeValue(parsedData.mule)
    };
    const lines = buildJSONLines(normalizedData);
    const aligned = alignLines(lines);
    const stats = calculateStats(aligned, context.exemptedFields);

    runTests(stats, context);
    logStatistics(stats);
    storeReport(context, stats);

    const isCollectionRunner = pm.info.iteration > 0;
    const isIndividualExecution = !isCollectionRunner;
    if (isIndividualExecution) {
        renderVisualizer(aligned, stats, context.requestName);
    }
}

// ========================================================================
// Top-level script: Poll and run workflow
// ========================================================================
const regressionMode = getRegressionMode();

if (shouldSkipRequest(pm.info.requestName, regressionMode)) {
    console.log(`Skipping utility request: ${pm.info.requestName}`);
    return;
}

logRegression(regressionMode);

const isCollectionRunner = pm.info.iteration > 0;
const isIndividualExecution = !isCollectionRunner;
console.log(`Request: ${pm.info.requestName}, Individual: ${isIndividualExecution}`);

const POLL_CONFIG = { maxAttempts: 20, interval: 500 };
let attempts = 0;

const getBoomiResponse = () => pm.collectionVariables.get("boomi_response");

const isValidResponse = (response) =>
    response && response !== "" && response !== "undefined" && response !== null;

const handleTimeout = () => {
    console.error("Boomi response timeout");
    pm.test("Boomi response received", () => {
        pm.expect.fail("Timeout waiting for Boomi response");
    });
    if (isIndividualExecution) {
        pm.visualizer.set(
            `<div style="padding:40px;text-align:center;font-family:Arial;background:#fff3cd">
                <h2>Timeout</h2>
                <p>Boomi response not received</p>
            </div>`
        );
    }
};

const waitForBoomiResponse = () => {
    attempts++;
    const boomiResponse = getBoomiResponse();
    if (isValidResponse(boomiResponse)) {
        executeComparison();
    } else if (attempts >= POLL_CONFIG.maxAttempts) {
        handleTimeout();
    } else {
        setTimeout(waitForBoomiResponse, POLL_CONFIG.interval);
    }
};

waitForBoomiResponse();
