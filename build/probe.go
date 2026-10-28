// SPDX-License-Identifier: GPL-3.0-only
// Bridge health adapter. API authentication and calls use the unmodified
// official TrueNAS client. No NAS data or upstream errors are printed.
package main

import (
    "encoding/json"
    "io"
    "log"
    "os"

    "github.com/truenas/truenas-mcp/truenas"
)

func main() {
    log.SetOutput(io.Discard)
    tlsConfig, err := truenas.NewTLSConfig(false, os.Getenv("TRUENAS_TLS_CA"))
    if err != nil { os.Exit(1) }
    client, err := truenas.NewClientWithOptions(os.Getenv("TRUENAS_URL"), os.Getenv("TRUENAS_API_KEY"), tlsConfig,
        truenas.Options{APIUser: os.Getenv("TRUENAS_API_USER"), Proxy: "none"})
    if err != nil { os.Exit(1) }
    defer client.Close()
    result, err := client.Call("system.info")
    if err != nil { os.Exit(1) }
    var info map[string]interface{}
    if json.Unmarshal(result, &info) != nil || len(info) == 0 { os.Exit(1) }
}
