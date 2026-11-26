// What the chat room and Stagehand's window draw the same way (`talk.js`).
//
// Each conversation wears its own classes on a shared row (`mmc-ch-*`,
// `mmc-sh-*`), so only what neither of them styles is here.

export const css = `
.mmc-talk-doors { display: flex; flex-wrap: wrap; gap: 8px; }
.mmc-talk-failtext { white-space: pre-wrap; overflow-wrap: anywhere; }
`;
