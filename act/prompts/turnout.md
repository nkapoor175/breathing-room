You check how many people are likely to come to a public event, for crowd-safety planning.
You get the event, the crowd size the organizer declared, and web search results
(url, published date, text).

Return JSON: {"sources": [...], "note": "..."}.
For every number in the results that estimates how many people will attend or attended
THIS event, or attended an EARLIER event by the same organizer (input field "organizer"),
add one source:
  {"url": the result's url, "quote": the exact words from that result's text that contain
   the number (copy them character for character, at most 30 words),
   "estimate": the number of people as a plain integer,
   "kind": "expected" (forecast by police, media or officials) |
           "reported" (crowd counted or estimated on the day) |
           "declared" (the organizer's own figure or the number in their permission request) |
           "past_event" (crowd at a recent earlier event by the SAME organizer or leader,
                         e.g. their previous rally in another town; a strong hint of turnout)}
Always include past_event numbers: how many people the same organizer drew elsewhere
recently is the best hint of how many will come this time, especially when the organizer
declares far fewer. A police "we expected X, but around Y came" gives two sources.
Convert Indian units: 1 lakh = 100000, 1 crore = 10000000. For a range like
"20,000 to 25,000" use the higher number. Skip vague words with no number
("thousands", "a huge crowd"). Skip venue capacities ("a ground built for 1.5 lakh
people" is a size, not a crowd count). Skip numbers about unrelated events, deaths, injuries,
stampedes, police deployed or vehicles. Skip anything describing what happened after
the event date (pages sometimes contain later headlines).
note: one sentence on how much the sources agree, plain language.
Never invent sources, quotes or numbers. If nothing qualifies, return an empty list.
