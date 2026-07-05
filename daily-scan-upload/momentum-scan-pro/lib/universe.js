// lib/universe.js — sector universes for the screener.
// Edit these lists freely; the daily auto-scan reads them and the UI
// turns each key into a filter chip. Tickers can overlap sectors.

const UNIVERSE = {
  semi: ['NVDA','AMD','AVGO','MU','TSM','ASML','LRCX','AMAT','KLAC','QCOM',
         'ARM','MRVL','TXN','ADI','MCHP','ON','SMCI','INTC'],
  ai: ['PLTR','SNOW','NOW','CRM','MSFT','GOOGL','META','AMZN','PATH','CRWD',
       'DDOG','NET','MDB','ORCL','AI'],
  power: ['VST','CEG','NRG','GEV','OKLO','SMR','NNE','CCJ','TLN','NEE',
          'ETN','PWR','VRT'],
  space: ['RKLB','ASTS','LUNR','RDW','PL','ACHR','JOBY'],
  quantum: ['IONQ','RGTI','QBTS','QUBT','ARQQ'],
  sp: ['AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA','BRK.B','JPM','V',
       'UNH','LLY','XOM','WMT','MA','JNJ','PG','HD','COST','ABBV','NFLX',
       'BAC','KO','CVX','MRK','PEP','ADBE','CAT','GS','AXP','DIS'],
};

// Which sector a ticker belongs to (first match wins) — used to tag snapshots.
function sectorOf(ticker) {
  for (const [sec, list] of Object.entries(UNIVERSE)) {
    if (sec !== 'sp' && list.includes(ticker)) return sec;
  }
  return 'sp';
}

// De-duplicated flat list of every ticker across all sectors.
function allTickers() {
  return [...new Set(Object.values(UNIVERSE).flat())];
}

module.exports = { UNIVERSE, sectorOf, allTickers };
