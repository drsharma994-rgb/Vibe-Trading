import { useState } from "react";
import {
  Radar,
  Loader2,
  TrendingUp,
  TrendingDown,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Info,
} from "lucide-react";
import { api, type ScannerRunResponse, type ScannerSetup } from "@/lib/api";
import { cn } from "@/lib/utils";

const TIMEFRAMES = ["15", "60", "240"];
const HIGHER_TIMEFRAMES = ["240", "1440"];

export function Scanner() {
  const [maxCoindcx, setMaxCoindcx] = useState(15);
  const [maxDelta, setMaxDelta] = useState(15);
  const [includeGold, setIncludeGold] = useState(true);
  const [timeframeMinutes, setTimeframeMinutes] = useState("60");
  const [higherTimeframeMinutes, setHigherTimeframeMinutes] = useState("240");
  const [minRr, setMinRr] = useState(2.0);
  const [solidOnly, setSolidOnly] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScannerRunResponse | null>(null);

  const run = async () => {
    setError(null);
    setLoading(true);
    try {
      const res = await api.runScanner({
        max_coindcx: maxCoindcx,
        max_delta: maxDelta,
        include_gold: includeGold,
        timeframe_minutes: timeframeMinutes,
        higher_timeframe_minutes: higherTimeframeMinutes,
        min_rr: minRr,
        solid_only: solidOnly,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to run scanner");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen p-6 lg:p-8">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <div className="flex items-center gap-3">
          <Radar className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-bold">Scanner</h1>
        </div>
        <p className="text-sm text-muted-foreground -mt-4">
          Cross-venue read-only scan across CoinDCX futures, Delta Exchange futures, and gold, ranked with
          a composite trend/momentum/volume signal plus a five-part confluence check. Informational only
          -- not investment advice, and no orders are ever placed.
        </p>

        {/* Controls */}
        <div className="flex flex-col gap-4 border rounded-lg p-4">
          <div className="flex flex-wrap gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium">Max CoinDCX pairs</label>
              <input
                type="number"
                min={1}
                max={50}
                value={maxCoindcx}
                onChange={(e) => setMaxCoindcx(Number(e.target.value))}
                className="w-28 px-3 py-2 rounded-md border bg-background text-sm"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium">Max Delta pairs</label>
              <input
                type="number"
                min={1}
                max={50}
                value={maxDelta}
                onChange={(e) => setMaxDelta(Number(e.target.value))}
                className="w-28 px-3 py-2 rounded-md border bg-background text-sm"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium">Timeframe (min)</label>
              <select
                value={timeframeMinutes}
                onChange={(e) => setTimeframeMinutes(e.target.value)}
                className="w-28 px-3 py-2 rounded-md border bg-background text-sm"
              >
                {TIMEFRAMES.map((tf) => (
                  <option key={tf} value={tf}>{tf}</option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium">Higher timeframe (min)</label>
              <select
                value={higherTimeframeMinutes}
                onChange={(e) => setHigherTimeframeMinutes(e.target.value)}
                className="w-28 px-3 py-2 rounded-md border bg-background text-sm"
              >
                {HIGHER_TIMEFRAMES.map((tf) => (
                  <option key={tf} value={tf}>{tf}</option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium">Min R:R</label>
              <input
                type="number"
                min={0.5}
                max={10}
                step={0.5}
                value={minRr}
                onChange={(e) => setMinRr(Number(e.target.value))}
                className="w-24 px-3 py-2 rounded-md border bg-background text-sm"
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-6">
            <label className="flex items-center gap-2 text-sm font-medium">
              <input
                type="checkbox"
                checked={includeGold}
                onChange={(e) => setIncludeGold(e.target.checked)}
              />
              Include gold (COMEX)
            </label>
            <label className="flex items-center gap-2 text-sm font-medium">
              <input
                type="checkbox"
                checked={solidOnly}
                onChange={(e) => setSolidOnly(e.target.checked)}
              />
              Solid setups only (3+ of 4 confirmations)
            </label>
          </div>

          <div>
            <button
              onClick={run}
              disabled={loading}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium disabled:opacity-50"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              {loading ? "Scanning..." : "Run Scanner"}
            </button>
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
            <XCircle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        {result && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Info className="h-3.5 w-3.5" />
              {result.disclaimer} · {result.count} setup{result.count === 1 ? "" : "s"} · generated {new Date(result.generated_at).toLocaleString()}
            </div>

            {result.setups.length === 0 ? (
              <div className="text-sm text-muted-foreground border rounded-lg p-6 text-center">
                No setups found for the current filters. Try widening the universe or lowering the R:R.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {result.setups.map((setup, i) => (
                  <SetupCard key={setup.venue + "-" + setup.symbol + "-" + i} setup={setup} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function SetupCard({ setup }: { setup: ScannerSetup }) {
  const isLong = setup.signal === "long";
  const families = setup.families ? Object.entries(setup.families) : [];

  return (
    <div className="flex flex-col gap-3 border rounded-lg p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-muted-foreground">{setup.venue}</span>
          <span className="font-semibold">{setup.symbol}</span>
        </div>
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
            isLong ? "bg-green-500/10 text-green-600" : "bg-red-500/10 text-red-600",
          )}
        >
          {isLong ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
          {setup.signal}
        </span>
      </div>

      {typeof setup.is_solid === "boolean" && (
        <span
          className={cn(
            "inline-flex w-fit items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
            setup.is_solid ? "bg-green-500/10 text-green-600" : "bg-amber-500/10 text-amber-600",
          )}
        >
          {setup.is_solid ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
          {setup.is_solid ? "Solid" : "Weak"} · {setup.confirmations}/{setup.of} confirmations
        </span>
      )}

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {setup.close !== undefined && <div>Close: <span className="text-foreground">{setup.close.toFixed(4)}</span></div>}
        {setup.rsi !== undefined && <div>RSI: <span className="text-foreground">{setup.rsi.toFixed(1)}</span></div>}
        {setup.adx !== undefined && <div>ADX: <span className="text-foreground">{setup.adx.toFixed(1)}</span></div>}
        {setup.volume_ratio !== undefined && <div>Vol ratio: <span className="text-foreground">{setup.volume_ratio.toFixed(2)}</span></div>}
      </div>

      {families.length > 0 && (
        <div className="flex flex-col gap-1 border-t pt-2">
          {families.map(([name, f]) => (
            <div key={name} className="flex items-center gap-2 text-xs">
              {f.pass ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-green-600 shrink-0" />
              ) : (
                <XCircle className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              )}
              <span className="font-medium">{name}</span>
              <span className="text-muted-foreground">— {f.detail}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
