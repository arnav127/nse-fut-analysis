r"""The manuscript text.

The prose is authored here; the numbers are not. Every quantity is a macro defined in
`macros.tex`, which `build_macros.py` generates from the recorded metrics, so changing a
model or reparsing a session updates the document wherever that quantity appears and nowhere
else. A literal numeral in this file is a defect - `audit_macros.py` fails the build on one.

Macro names follow the recorded key: `spread.mean_bps_expiry` is `\SpreadMeanBpsExpiry`, and
digits are spelled out because LaTeX command names cannot contain them, so H12's p-value is
`\HHOneTwoPValue`.

Numbers that are part of the document's own structure rather than a finding - a figure
width, a column count - are not macros. Those are typography.
"""

from __future__ import annotations

PREAMBLE = r"""\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[top=1in,bottom=1in,left=0.9in,right=0.9in]{geometry}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{graphicx}
\usepackage{xcolor}
\usepackage{amsmath}
\usepackage{hyperref}
\usepackage{caption}
\definecolor{deepnavy}{RGB}{26,54,93}
\definecolor{sectionblue}{RGB}{43,108,176}
\hypersetup{colorlinks=true,linkcolor=deepnavy,urlcolor=sectionblue,citecolor=deepnavy}
\captionsetup{font=small,labelfont=bf}
\setlength{\parskip}{0.4em}

\input{macros}

\title{\textbf{\color{deepnavy} Expiry-Day Microstructure and the Settlement VWAP\\
\large An order-level study of the National Stock Exchange of India}}
\author{Arnav Dixit}
\date{\today}
"""

ABSTRACT = r"""\begin{abstract}
\noindent
Equity derivatives on the National Stock Exchange of India settle at the volume-weighted
average price of the underlying cash market over the final thirty minutes of trading. That
design gives anyone holding a large expiring position a direct financial interest in the
cash market over a known, narrow window. We ask what the order book actually does in that
window.

The study uses order-by-order (Level 3) data rather than quotes or trades alone, so that
order entry, modification and cancellation are observed individually and the book can be
reconstructed rather than inferred. We compare each of \DesignExpirySessions{} monthly
expiry Thursdays in 2022 against a matched control session in the same month, across
\DesignSymbols{} equities split into a liquid and an illiquid group, and specify
\TestSpecified{} hypotheses about spreads, depth, order aggression, cancellation behaviour,
concealed size, price impact and resilience.

The sample comprises \SampleOrderEventsMillions{} million order events and
\SampleTradesMillions{} million trades for the study universe, drawn from
\SampleOrderEventsRead{} order records across \SampleSessionsParsed{} sessions, from which
\SampleSnapshots{} one-second reconstructions of the limit order book are built at
\DesignBookLevels{} levels per side.

\ResultsHeadline{}
\end{abstract}
"""

INTRODUCTION = r"""\section{Introduction}

A settlement price that is computed from the market it settles is a standing invitation to
influence that market. The magnitude of the invitation depends on the design: a single
closing print is cheap to move and correspondingly easy to police, while an average over a
long window is expensive to move and hard to detect. The National Stock Exchange of India
sits between these, settling equity derivatives at the volume-weighted average price (VWAP)
of the underlying cash market over the last thirty minutes of the expiry session.

Whether that window behaves differently is an empirical question, and the answer is not
obvious in either direction. Expiry brings genuine hedging and roll activity that has
nothing to do with influencing the settlement, and that activity alone would widen spreads
and thin the book. Distinguishing the two requires a comparison, which is why every
quantity in this paper is measured against a matched control session rather than against an
absolute benchmark.

We depart from most of the literature in one respect that turns out to matter. Studies of
settlement windows typically work from trade prints and top-of-book quotes. Those show what
happened but not what was attempted: an order entered and cancelled within a second leaves
no trace in a trade file, and a large order shown a slice at a time looks like a series of
small ones. Order-by-order data records entry, modification and cancellation as separate
events with participant and routing attributes attached, which makes both of those visible.
Two of our measures - the rate of orders resting under one second, and the share of volume
held back from display - cannot be constructed from trade data at all.

Section~\ref{sec:background} describes the settlement mechanism. Section~\ref{sec:data}
describes the data and how the book is reconstructed. Section~\ref{sec:design} sets out the
matched design and Section~\ref{sec:method} the measures and tests.
Section~\ref{sec:results} reports what we find, and Section~\ref{sec:limits} is explicit
about what this design cannot establish.
"""

BACKGROUND = r"""\section{Institutional background}\label{sec:background}

Equity futures and options on the National Stock Exchange expire on the last Thursday of
each calendar month. The settlement price for stock futures is the volume-weighted average
price of the underlying security in the cash market between \DesignWindowStart{} and
\DesignWindowEnd{} IST, a window of \DesignWindowMinutes{} minutes ending at the close.

Three features of this design shape what follows. The window is known in advance, so
positioning can be planned rather than improvised. It is short enough that a determined
participant's own volume can be a material share of it, particularly in a less liquid name.
And because the settlement is an average rather than a single print, influencing it requires
sustained participation across the window rather than one aggressive order at the close -
which means the footprint, if there is one, should be visible in the shape of activity
across the thirty minutes and not only at its end.

The cash market operates a continuous limit order book with price-time priority. Two
order-level features are directly relevant. A disclosed-quantity instruction lets a
participant display less than the full size of an order; the undisplayed remainder
replenishes as the visible slice fills, and each replenishment loses queue priority. An
immediate-or-cancel instruction executes whatever is available at submission and cancels the
rest, which is the standard way to take liquidity without leaving a resting order behind.
Both are recorded in the order feed, and both are measured here.
"""

DATA = r"""\section{Data}\label{sec:data}

\subsection{Source and scale}

The exchange publishes complete order and trade files for each session: every order entry,
modification and cancellation, and every resulting trade, with microsecond timestamps. These
are Level 3 (market-by-order) records, not aggregated depth. Each order record carries the
side, the total and disclosed quantities, the limit price, the immediate-or-cancel and
market flags, a participant classification (custodian, proprietary, or non-custodian
non-proprietary) and a routing classification (algorithmic or manual, each with or without
smart order routing). Each trade record names both sides' order numbers, so trades can be
attributed back to the orders that produced them.

Across \SampleSessionsParsed{} sessions the raw feed contains \SampleOrderEventsRead{}
equity-series order records and \SampleTradesRead{} trade records. Restricting to the study
universe leaves \SampleOrderEvents{} order events and \SampleTrades{} trades, or
\SampleUniverseSharePct{}\% of all equity-series order activity.

\subsection{Decoding}

The files are fixed-width binary with a layout that has changed across specification
revisions. Timestamps are stored as jiffies, a count of \(1/65536\) second intervals from
1980-01-01; prices are integer paise; the ten-byte symbol field is right-aligned and padded.
Decoding is performed by \texttt{nsetick}, which holds the byte layouts in a versioned
specification, selects the record version by session date and validates that choice against
the observed record length, so a mis-sliced record is reported rather than silently
producing plausible wrong values. The manuscript's sample counts are read from the decoder's
own manifests, not from the configuration, so they describe what was actually parsed.

\subsection{Book reconstruction}

The limit order book is rebuilt for each security and session by replaying its order events
in sequence, and snapshotted every \DesignSnapshotInterval{} second at \DesignBookLevels{}
price levels per side. The replay honours disclosed-quantity behaviour: only the displayed
slice rests in the visible book, the concealed remainder replenishes as that slice fills,
and the replenished portion loses queue priority. This matters for the measurement rather
than only for realism. Resting the full size of a disclosed-quantity order would overstate
visible depth at exactly the prices where large orders sit, which is where the depth
measures in Section~\ref{sec:results} are taken.

The snapshot retained for analysis covers the settlement window and reports, at each level,
displayed size and concealed size separately, together with the events that occurred since
the previous snapshot. Books are replayed from the session open rather than from
\DesignWindowStart{}, since a book started at the window's open would contain only what
arrived after it. Reconstruction yields \SampleSnapshots{} settlement-window snapshots across
\SampleSnapshotSymbols{} securities.
"""

DESIGN = r"""\section{Research design}\label{sec:design}

\subsection{Matched sessions}

Each of the \DesignExpirySessions{} expiry Thursdays in 2022 is paired with a control
session in the same calendar month, giving \DesignSessions{} sessions in total. Pairing
within the month holds the broad market environment approximately fixed: the same
macroeconomic backdrop, the same index level, the same participants. Every test in this
paper is paired at the level of a security and a month, so a security that is simply more
active than another contributes nothing to the comparison.

\subsection{Universe}

The study covers \DesignSymbols{} securities, split into a liquid group
(\DesignLiquidList{}) and an illiquid group (\DesignIlliquidList{}). The split is
deliberate rather than incidental. If the settlement window is being influenced, the cost of
doing so falls with liquidity, so the effect should be larger where the book is thinner -
and a difference that appears in both groups equally is more consistent with ordinary
expiry-day hedging than with anything targeted at the settlement price.

\subsection{Window}

All measures are computed over \DesignWindowStart{} to \DesignWindowEnd{} IST. Where a
measure compares the window against the rest of the session, it is expressed as a rate per
minute rather than as a total, since the window is \DesignWindowMinutes{} minutes against
roughly three hundred and forty-five for the remainder and a comparison of sums would
reflect the length difference rather than any difference in behaviour.

Pre-open auction records share the session file with continuous trading. They are excluded
from every return series, since the first continuous-session observation would otherwise be
differenced against the auction price and book the entire overnight move as one minute of
intraday variance.
"""

METHOD = r"""\section{Measures and inference}\label{sec:method}

\subsection{Measures}

\textbf{Spreads and depth.} The quoted spread is measured at each one-second snapshot and
averaged over the window. Depth is displayed size summed over the top \DesignReportedLevels{}
levels of each side; the book imbalance is the normalised difference between the two sides.

\textbf{Order aggression.} The immediate-or-cancel share is the fraction of entered orders
carrying that instruction; the aggressive share adds market orders. Both are computed per
minute and per security, and the final five minutes are reported separately from the rest of
the window, since a hypothesis about acceleration towards the close is not the same as a
hypothesis about the window as a whole.

\textbf{Cancellation behaviour.} The cancel-to-entry ratio counts cancellations per entry.
Order lifespan is measured from an order's entry to its cancellation, and orders resting
under one second are reported separately: an order that cannot realistically be executed
against is displaying liquidity rather than offering it.

\textbf{Concealed size.} An order is treated as carrying concealed size when its disclosed
quantity is positive and below its total. A disclosed quantity of zero indicates no
disclosure instruction at all, which is the ordinary case and not concealment; conflating
the two would classify most of the book as concealed.

\textbf{Price impact.} Kyle's lambda is estimated by regressing the price change over each
minute on signed volume for that minute, with trade direction assigned by the tick rule and
zero-tick trades inheriting the previous direction. Signing is essential and not cosmetic:
buys and sells of equal size move price in opposite directions, so a regression on unsigned
volume has a regressor that carries no direction and returns a coefficient near zero
whatever the true impact.

\textbf{Resilience.} A spread widening beyond twice the session's median spread opens an
episode, which closes when the spread returns inside 1.5 times the median. Consecutive
elevated seconds form one episode rather than one per second, and the baseline is the median
rather than the mean so that it is not pulled up by the episodes being measured.

\subsection{Inference}

Every hypothesis takes the same form: a per-security quantity on an expiry session against
the same quantity on that month's control session. Each results file is reduced to one value
per security and session before pairing, so a security contributes one matched pair per
month. Tests are paired \(t\)-tests, with a Wilcoxon signed-rank test reported alongside,
since these distributions are heavy-tailed and a result that survives both is worth
distinguishing from one that depends on normality. Effect sizes are Cohen's \(d\) on the
paired differences.

Of \TestSpecified{} hypotheses specified, \TestEvaluated{} could be evaluated on the
available data, over \TestPairsTotal{} matched security-session pairs. Testing many
hypotheses on one sample inflates the chance of a spurious rejection, so significance is
assessed under Benjamini-Hochberg control of the false discovery rate at
\(\alpha = \TestAlpha{}\), applied across the hypotheses actually tested. The Bonferroni
count is reported alongside as the conservative alternative.
"""

RESULTS_INTRO = r"""\section{Results}\label{sec:results}

\subsection{The settlement window}

Table~\ref{tab:stylised} reports the descriptive picture: for each quantity, the mean across
expiry sessions, the mean across control sessions, and the difference. Reading it against
Table~\ref{tab:tests}, which gives the paired tests, separates quantities that differ by an
economically interesting amount from those that merely differ reliably.

\subsection{Hypothesis tests}

Table~\ref{tab:tests} reports all \TestSpecified{} hypotheses. \TestEvaluated{} were
evaluated; the remainder lacked inputs and are marked as untested rather than as null
results, since the two are not the same thing and a reader cannot distinguish them from a
blank cell. \TestRejectedFdr{} are rejected under false discovery rate control and
\TestRejectedBonferroni{} under the Bonferroni threshold.

Rejection and support are reported separately, because they are not the same thing. The
paired test is two-sided: a small $p$-value says the quantity differs between expiry and
control sessions, not that it differs in the direction the hypothesis claims.
\TestSupported{} hypotheses are rejected with the effect pointing as stated
(\TestSupportedIds{}). \TestContradicted{} are rejected with the effect pointing the other
way (\TestContradictedIds{}) - these have been refuted, not confirmed, and counting them
among the confirmations would invert their meaning. The remaining \TestNotRejected{}
evaluated hypotheses are not distinguishable from no difference.

\subsection{Reading the effect sizes}

Effect sizes are the quantity to read here, not the $p$-values. With \TestPairsTotal{}
matched pairs a test has power to detect differences far smaller than anything economically
interesting, so significance alone establishes very little. Cohen's $d$ across the supported
hypotheses is modest: the largest is \HHEightEffectSizeCohenD{} (H8, cancellation counts),
and the settlement window's spread difference of \SpreadMeanBpsDiff{} basis points against a
control-session level of \SpreadMeanBpsControl{} is a real but small widening.

The two contradicted hypotheses are informative rather than embarrassing, and they point the
same way. H7 predicted that cancellations per entry would spike; they fall. H8 shows the
cancellation \emph{count} rising at the same time, so entries must be rising faster still -
the window attracts more order submission of every kind, not a disproportionate amount of
placing and pulling. H18 predicted that book pressure would become more persistent; it
becomes less so, which is what one expects when more participants are active on both sides
rather than when one side is leaning on the book.

Set against that, the hypotheses that speak most directly to directional pressure are the
ones that fail to reject. Depth is not reliably eroded (H14), order flow imbalance does not
rise (H16), and traded volume is no more concentrated into the window's closing minutes than
on a control session (H29). The differences that do appear sit in the mechanics of order
handling: wider spreads (H12), more concealed size (H9), more orders withdrawn inside a
second (H28), higher price impact (H17), a higher variance rate (H24), and spreads that
recover from a widening faster rather than slower (H30). That combination is the signature
of heavier and more automated participation in a known window, which is what expiry-day
hedging and rolling would also produce.
"""

LIMITATIONS = r"""\section{What this design cannot establish}\label{sec:limits}

\textbf{It cannot establish intent.} Every measure here is consistent with deliberate
positioning around the settlement price and equally consistent with ordinary hedging and
roll activity concentrated in the same window for unrelated reasons. The matched design
removes the market environment as an explanation; it does not remove expiry-day hedging,
which is a real and legitimate source of exactly the activity being measured. Nothing in
this paper identifies manipulation, and it should not be read as doing so.

\textbf{The universe is small.} \DesignSymbols{} securities, chosen to span a liquidity
range, is enough to detect a difference but not enough to characterise the cross-section.
The liquid and illiquid groups have \DesignLiquidSymbols{} and \DesignIlliquidSymbols{}
members respectively, so any statement about how an effect varies with liquidity rests on a
comparison of two small groups and should be treated as suggestive.

\textbf{One year.} All \DesignSessions{} sessions fall in 2022. Whether these patterns
persist across regimes, or reflect that year's volatility in particular, is not something a
single year can answer.

\textbf{Participant classification is coarse.} The feed distinguishes custodian,
proprietary and other, which does not identify individual participants or link activity
across securities. A participant hedging one position across several names is invisible as
such.

\textbf{Derivatives positions are not observed.} Without open interest and roll data the
link between a security's expiring position and its cash-market behaviour cannot be tested
directly. The hypotheses that would have tested it are listed as untested in
Table~\ref{tab:tests}.
"""

REPRODUCIBILITY = r"""\section{Reproducibility}

Every number in this document is generated. Each quantity is recorded by the code that
computes it, written to a metrics file with its unit and a note describing the computation,
and reaches this document only as a macro; no figure is typed in by hand. Rerunning the
pipeline after any change updates each number that changed and leaves the rest untouched,
and the build fails if the text cites a quantity that was never recorded.

The appendix records the commit of each repository, the library versions and the input file
manifest behind this particular run. The pipeline runs end to end from one command.
"""
