# Logic 2 MCP server — tool list

Enumerated from Logic 2.4.46 on 2026-09-21 with `slt mcp-tools --json`; full
schemas are in `mcp-tools.json`. Server: Streamable HTTP, `http://127.0.0.1:10530`,
enabled under Settings > Automation. The repo's `.mcp.json` registers it for
Claude Code as `logic2`.

| Tool | Description | Parameters |
|---|---|---|
| `get_devices` | List connected Saleae devices | `includeSimulationDevices`? |
| `start_capture` | Start a new capture | `deviceId`?, `logicDeviceConfiguration`?, `captureConfiguration`? |
| `stop_capture` | Stop an active capture | `captureId` |
| `wait_capture` | Wait for a capture to complete. This call blocks until the capture finishes and may take minutes — configure your HTTP client timeout accordingly. | `captureId` |
| `load_capture` | Load a capture from a .sal file | `filepath` |
| `save_capture` | Save a capture to a .sal file | `captureId`, `filepath` |
| `close_capture` | Close a capture and free resources | `captureId` |
| `add_analyzer` | Add a protocol analyzer to a capture | `captureId`, `analyzerName`, `analyzerLabel`?, `settings`? |
| `remove_analyzer` | Remove a protocol analyzer from a capture | `captureId`, `analyzerId` |
| `add_high_level_analyzer` | Add a high-level analyzer to a capture | `captureId`, `extensionDirectory`, `hlaName`, `hlaLabel`?, `inputAnalyzerId`, `settings`? |
| `remove_high_level_analyzer` | Remove a high-level analyzer from a capture | `captureId`, `analyzerId` |
| `export_raw_data_csv` | Export raw capture data as CSV files | `captureId`, `directory`, `logicChannels`?, `analogDownsampleRatio`, `iso8601Timestamp`? |
| `export_raw_data_binary` | Export raw capture data as binary files | `captureId`, `directory`, `logicChannels`?, `analogDownsampleRatio` |
| `export_data_table_csv` | Export analyzer results as a CSV data table | `captureId`, `filepath`, `analyzers`?, `iso8601Timestamp`?, `exportColumns`?, `filter`? |
| `legacy_export_analyzer` | Export analyzer data in legacy format | `captureId`, `filepath`, `analyzerId`, `radixType` |

`?` marks optional parameters.

The set mirrors the gRPC Automation API one-to-one (devices, capture lifecycle,
analyzers, exports). There is no tool that returns decoded frames inline; the
loop is export to a file, then read the file. `saleae_tools.binexport` covers
the binary export.
