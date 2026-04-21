# Postman API Comparison Framework

## Overview

Automated comparison framework for JSON API responses between Boomi and MuleSoft platforms with advanced features including LCS-based array alignment, field exemption, large payload handling, and comprehensive reporting.

## Key Features

- **Intelligent Array Alignment**: LCS (Longest Common Subsequence) algorithm for accurate array element comparison
- **Field Exemption System**: Exclude dynamic fields (timestamps, IDs, etc.) from comparison using simple pattern matching
- **Large Payload Support**: Optional flag to skip logging response bodies while maintaining full comparison functionality
- **Side-by-Side Visualization**: Interactive HTML visualizer with color-coded differences
- **Detailed Statistics**: Match percentages, line-by-line counts, and exemption tracking
- **CSV Export**: Generate summary and full detailed reports with complete cURL commands
- **Production-Ready**: Proper escaping for JSON/CSV, compact ES6 syntax, no external dependencies

## Setup

### Collection Variables

Required collection variables:

| Variable | Type | Description | Default |
|----------|------|-------------|---------|
| `exempted_fields` | JSON Array | List of field names to exempt from comparison | `[]` |
| `skip_payload_logging` | String | Set to `"true"` to skip logging large response bodies | `"false"` |
| `report_request_count` | Number | Tracks number of requests in collection run | Auto-set |
| `current_report_index` | Number | Current request index during collection run | Auto-set |

## Usage

### Basic Execution

**Individual Request:**
1. Execute any request in the collection
2. View side-by-side comparison in Visualizer tab
3. Check Tests tab for pass/fail status

**Collection Run:**
1. Use Collection Runner
2. Execute all requests
3. Run final "Generate Report" request
4. Export CSV from visualizer

### Field Exemption

Exempt dynamic fields that always differ between systems:

```
[
  "timestamp",
  "transactionId",
  "uuid",
  "createdAt",
  "lastModified"
]
```

**How it works:**
- Any field path containing these strings will be marked as "exempted"
- Exempted fields don't count as mismatches
- Still visible in visualizer with yellow highlight
- Statistics track exempted line count separately

**Examples:**
- `"timestamp"` exempts: `order.timestamp`, `header.timestamp`, `timestamp`
- `"order.id"` exempts: `order.id` but not `customer.order.orderId`

### Large Payload Handling

 Skip logging response bodies for large payloads while maintaining full comparison.

#### When to Use
- Response bodies > 200KB
- Binary or base64-encoded data in responses
- Collection runs with many large requests
- When CSV export size becomes problematic

#### How to Enable

**Option 1: Per-Request (Recommended)**

Add to specific request's Pre-request Script:
```
// Skip payload logging for this large response
pm.collectionVariables.set("skip_payload_logging", "true");
```

**Option 2: Collection-Wide**

Add to Collection Pre-request Script:
```
// Skip payload logging for all requests
pm.collectionVariables.set("skip_payload_logging", "true");
```

#### What Happens When Enabled
- Full comparison executes normally
- Visualizer shows complete side-by-side view
- All test assertions run
- Statistics calculated accurately
- CSV reports show `[PAYLOAD_SKIPPED]` instead of response body
- cURL commands still logged in full
- Significant reduction in collection variable storage

#### Re-enabling Payload Logging

```
// Re-enable for next request
pm.collectionVariables.set("skip_payload_logging", "false");
pm.collecitonVariables.unset("skip_payload_logging");
```

### Report Generation

After collection run, execute "Generate Report" request:

**Summary CSV** (Lightweight)
- Request names, status, statistics
- No response bodies or cURL commands
- Ideal for quick analysis

**Full CSV** (Complete)
- All fields from Summary CSV
- Complete cURL commands
- Full response bodies (unless skipped)
- Ideal for debugging and documentation

**Copy Buttons:**
- Click "Copy Summary CSV" or "Copy Full CSV"
- Paste into Excel, Google Sheets, or text editor
- Data is properly escaped for CSV format


## Statistics Explained

| Metric | Description |
|--------|-------------|
| **Total Lines** | Number of JSON lines compared |
| **Matched** | Lines with identical content |
| **Mismatched** | Lines with differences (comparison fails) |
| **Exempted** | Lines matching exemption patterns (ignored) |
| **Only Boomi** | Lines present only in Boomi response |
| **Only Mule** | Lines present only in MuleSoft response |
| **Match %** | (Matched / Total) × 100 |
| **Status** | PASSED (no mismatches) or FAILED |

## Advanced Features

### Array Alignment

The framework uses LCS algorithm to intelligently align array elements, even when order differs:

```
// Boomi: ["apple", "banana", "cherry"]
// Mule:  ["banana", "cherry", "apple"]
// Result: All matched correctly despite different order
```

### Escape Handling

Automatic escaping for:
- JSON special characters: `"`, `\`, `\n`, `\r`, `\t`
- CSV delimiters: `,`, `"`, newlines
- Backslash sequences in string values
- Unicode characters preserved

### Visualizer Features

- Color-coded rows (green=match, red=mismatch, yellow=exempted)
- Indentation shows JSON structure
- Arrow indicators for one-sided differences
- Sticky header for large responses
- Responsive design for 14" laptop displays

## Best Practices

1. **Start with individual requests** to validate comparison logic before collection runs
2. **Use exemptions sparingly** - only for truly dynamic fields
3. **Enable payload skipping** for responses >200KB to avoid storage issues
4. **Review visualizer** before trusting automated test results
5. **Export both CSV formats** - Summary for quick review, Full for debugging
6. **Clear reports between runs** using setup script
7. **Test exemption patterns** on individual requests first
8. **Monitor response sizes** and enable skipping proactively

## Troubleshooting

### High Mismatch Count
- Review exempted_fields - are dynamic fields properly excluded?
- Check if APIs return consistent data structures
- Verify array ordering differences aren't causing false mismatches

### Performance Issues
- Enable `skip_payload_logging` for large responses
- Reduce concurrent requests in Collection Runner
- Check Postman's max response size settings (Settings → General)

### CSV Export Failures
- Response bodies too large: Enable `skip_payload_logging`
- Collection variable limits: Use Summary CSV instead of Full
- Special characters: Framework handles automatically, but check for corrupted data

### Visualizer Not Rendering
- Response timeout: Increase max timeout in settings
- JavaScript errors: Check browser console for details
- Too many lines: Framework tested up to 10,000+ lines

### Exemptions Not Working
- Verify `exempted_fields` is valid JSON array
- Field names are case-sensitive
- Patterns match partial paths (e.g., "id" matches "order.id")

## Limitations

- JSON-only comparison (use separate collection for XML/SOAP)
- Pattern matching is substring-based (no regex support)
- Maximum response size limited by Postman (default 50MB)
- Collection variables have storage limits (~5MB recommended per variable)

## Version History

- **2025-10-28**: Added large payload skipping feature
- **2025-10-27**: Initial production release with LCS array alignment

## Support

For issues, enhancements, or questions:
- Review inline script comments
- Check console logs during execution
- Adjust comparison logic for specific API requirements
- Modify exemption patterns as needed

---

**Production-Ready Framework** | **No External Dependencies** 