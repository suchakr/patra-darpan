#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import readline from "node:readline/promises";
import { fileURLToPath } from "node:url";
import SearchCore from "../../web/assets/js/search-core.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, "../..");
const DEFAULT_CORPUS = path.join(ROOT, "web/assets/data/search-corpus.json");

function usage() {
  return `Patra Darpan Search Lab CLI

Usage:
  node tools/search-lab/search-cli.mjs [options] <query>
  node tools/search-lab/search-cli.mjs --interactive

Options:
  --help              Show this help.
  --corpus PATH       Search corpus JSON path.
                      Default: web/assets/data/search-corpus.json
  --limit N           Maximum results to print. Default: 5.
  --json              Emit machine-readable JSON for one-shot query mode.
  --interactive       Start a local prompt for repeated queries.

Examples:
  node tools/search-lab/search-cli.mjs "Yājñavalkya cycle"
  node tools/search-lab/search-cli.mjs --json "Saptarṣi era"
  node tools/search-lab/search-cli.mjs --interactive
  node tools/search-lab/search-cli.mjs --corpus /tmp/search-corpus.json "magic square"
`;
}

function parseArgs(argv) {
  const options = {
    corpus: DEFAULT_CORPUS,
    limit: 5,
    json: false,
    interactive: false,
    help: false,
    queryParts: [],
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--help" || arg === "-h") {
      options.help = true;
    } else if (arg === "--corpus") {
      i += 1;
      if (!argv[i]) throw new Error("--corpus requires a path");
      options.corpus = path.resolve(argv[i]);
    } else if (arg === "--limit") {
      i += 1;
      if (!argv[i]) throw new Error("--limit requires a number");
      options.limit = Number(argv[i]);
      if (!Number.isFinite(options.limit) || options.limit < 1) {
        throw new Error("--limit must be a positive number");
      }
    } else if (arg === "--json") {
      options.json = true;
    } else if (arg === "--interactive") {
      options.interactive = true;
    } else if (arg.startsWith("--")) {
      throw new Error(`Unknown option: ${arg}`);
    } else {
      options.queryParts.push(arg);
    }
  }
  return options;
}

function loadCorpus(corpusPath) {
  if (!fs.existsSync(corpusPath)) {
    throw new Error(`Missing search corpus: ${corpusPath}`);
  }
  return JSON.parse(fs.readFileSync(corpusPath, "utf8"));
}

function asJsonResult(result, chunkMap) {
  const chunk = result.chunk;
  return {
    score: result.score,
    matched_terms: result.matched_terms,
    chunk_id: chunk.chunk_id,
    doc_id: chunk.doc_id,
    title: chunk.title,
    author_display: chunk.author_display,
    year: chunk.year,
    heading_path: chunk.heading_path || [],
    neighbors: SearchCore.getNeighborHeadings(chunk, chunkMap),
    snippet: result.snippet,
    source_url: chunk.source_url,
    gcs_key: chunk.gcs_key,
    quality_status: chunk.quality_status,
    quality_warnings: chunk.quality_warnings || [],
  };
}

function printTextResults(corpus, query, options) {
  const chunkMap = SearchCore.buildChunkMap(corpus);
  const results = SearchCore.search(corpus, query, { limit: options.limit });
  const metadata = corpus.metadata || {};

  if (options.json) {
    console.log(
      JSON.stringify(
        {
          query,
          metadata,
          result_count: results.length,
          results: results.map((result) => asJsonResult(result, chunkMap)),
        },
        null,
        2,
      ),
    );
    return;
  }

  console.log(`Search Lab corpus: ${metadata.doc_count || 0} docs, ${metadata.chunk_count || 0} chunks`);
  console.log(`Query: ${query}`);
  console.log("");

  if (!results.length) {
    console.log("No hits.");
    return;
  }

  results.forEach((result, index) => {
    const chunk = result.chunk;
    const heading = SearchCore.headingText(chunk) || "(no heading)";
    const neighbors = SearchCore.getNeighborHeadings(chunk, chunkMap);
    console.log(`${index + 1}. ${chunk.title || chunk.doc_id}`);
    console.log(`   ${chunk.author_display || "Unknown author"}${chunk.year ? `, ${chunk.year}` : ""}`);
    console.log(`   score=${result.score.toFixed(1)} chunk=${chunk.chunk_id}`);
    console.log(`   heading: ${heading}`);
    if (neighbors.prev) console.log(`   prev: ${neighbors.prev.heading || neighbors.prev.chunk_id}`);
    if (neighbors.next) console.log(`   next: ${neighbors.next.heading || neighbors.next.chunk_id}`);
    if (chunk.quality_warnings && chunk.quality_warnings.length) {
      console.log(`   warnings: ${chunk.quality_warnings.join(", ")}`);
    }
    console.log(`   ${result.snippet}`);
    console.log("");
  });
}

async function runInteractive(corpus, options) {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  const metadata = corpus.metadata || {};
  console.log(`Search Lab corpus: ${metadata.doc_count || 0} docs, ${metadata.chunk_count || 0} chunks`);
  console.log("Enter a query. Empty input exits.");
  while (true) {
    const query = (await rl.question("search> ")).trim();
    if (!query) break;
    printTextResults(corpus, query, { ...options, json: false });
  }
  rl.close();
}

async function main() {
  let options;
  try {
    options = parseArgs(process.argv.slice(2));
  } catch (error) {
    console.error(error.message);
    console.error("");
    console.error(usage());
    return 2;
  }

  if (options.help) {
    console.log(usage());
    return 0;
  }

  const query = options.queryParts.join(" ").trim();
  if (!options.interactive && !query) {
    console.error("Missing query. Use --help for examples.");
    return 2;
  }

  const corpus = loadCorpus(options.corpus);
  if (options.interactive) {
    await runInteractive(corpus, options);
  } else {
    printTextResults(corpus, query, options);
  }
  return 0;
}

main()
  .then((code) => {
    process.exitCode = code;
  })
  .catch((error) => {
    console.error(error && error.stack ? error.stack : String(error));
    process.exitCode = 1;
  });
