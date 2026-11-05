\version "2.20.0"
#(set-global-staff-size 20)

% un-comment the next line to remove Lilypond tagline:
% \header { tagline="" }

% comment out the next line if you're debugging jianpu-ly
% (but best leave it un-commented in production, since
% the point-and-click locations won't go to the user input)
\pointAndClickOff

\paper {
  print-all-headers = ##t %% allow per-score headers

  % un-comment the next line for A5:
  % #(set-default-paper-size "a5" )

  % un-comment the next line for no page numbers:
  % print-page-number = ##f

  % un-comment the next 3 lines for a binding edge:
  % two-sided = ##t
  % inner-margin = 20\mm
  % outer-margin = 10\mm

  % un-comment the next line for a more space-saving header layout:
  % scoreTitleMarkup = \markup { \center-column { \fill-line { \magnify #1.5 { \bold { \fromproperty #'header:dedication } } \magnify #1.5 { \bold { \fromproperty #'header:title } } \fromproperty #'header:composer } \fill-line { \fromproperty #'header:instrument \fromproperty #'header:subtitle \smaller{\fromproperty #'header:subsubtitle } } } }
}

%% 2-dot and 3-dot articulations
#(append! default-script-alist
   (list
    `(two-dots
       . (
           (script-priority . -200)
           (stencil . ,ly:text-interface::print)
           (text . ,#{ \markup \override #'(font-encoding . latin1) \center-align \bold ":" #})
           (padding . 0.20)
           (avoid-slur . inside)
           (side-axis . ,Y)
           (direction . ,UP)))))
#(append! default-script-alist
   (list
    `(three-dots
       . (
           (script-priority . -200)
           (stencil . ,ly:text-interface::print)
           (text . ,#{ \markup \override #'(font-encoding . latin1) \center-align \bold "⋮" #})
           (padding . 0.30)
           (avoid-slur . inside)
           (side-axis . ,Y)
           (direction . ,UP)))))
"two-dots" =
#(make-articulation 'two-dots)

"three-dots" =
#(make-articulation 'three-dots)

\layout {
  \context {
    \Score
    scriptDefinitions = #default-script-alist
  }
}

note-mod =
#(define-music-function
     (text note)
     (markup? ly:music?)
   #{
     \tweak NoteHead.stencil #ly:text-interface::print
     \tweak NoteHead.text
        \markup \lower #0.5 \sans \bold #text
     \tweak Rest.stencil #ly:text-interface::print
     \tweak Rest.text
        \markup \lower #0.5 \sans \bold #text
     #note
   #})

#(define (jianpu-glissando grob)
   (let* ((left-note (ly:spanner-bound grob LEFT))
          (right-note (ly:spanner-bound grob RIGHT))
          (left-y (ly:grob-property left-note 'Y-offset 0))
          (right-y (ly:grob-property right-note 'Y-offset 0))
          (left-event (ly:grob-property left-note 'cause))
          (right-event (ly:grob-property right-note 'cause))
          (left-pitch (and (ly:stream-event? left-event)
                           (ly:event-property left-event 'pitch)))
          (right-pitch (and (ly:stream-event? right-event)
                            (ly:event-property right-event 'pitch))))
     (if (and left-pitch right-pitch)
         (let* ((left-y-off (if (ly:pitch<? left-pitch right-pitch) (- left-y 0.9) (if (ly:pitch<? right-pitch left-pitch) (+ left-y 1.5) left-y)))
                (right-y-off (if (ly:pitch<? left-pitch right-pitch) (+ right-y 0.9) (if (ly:pitch<? right-pitch left-pitch) (- right-y 1.5) right-y)))
                (bd (ly:grob-property grob 'bound-details))
                (left-bd (list-copy (assoc-get 'left bd '())))
                (right-bd (list-copy (assoc-get 'right bd '())))
                (new-left-bd (assoc-set! left-bd 'Y left-y-off))
                (new-right-bd (assoc-set! right-bd 'Y right-y-off))
                (new-bd (list (cons 'left new-left-bd) (cons 'right new-right-bd))))
           (ly:grob-set-property! grob 'bound-details new-bd)))))
#(define (flip-beams grob)
   (ly:grob-set-property!
    grob 'stencil
    (ly:stencil-translate
     (let* ((stl (ly:grob-property grob 'stencil))
            (centered-stl (ly:stencil-aligned-to stl Y DOWN)))
       (ly:stencil-translate-axis
        (ly:stencil-scale centered-stl 1 -1)
        (* (- (car (ly:stencil-extent stl Y)) (car (ly:stencil-extent centered-stl Y))) 0) Y))
     (cons 0 -0.8))))

%=======================================================
#(define-event-class 'jianpu-grace-curve-event 'span-event)

#(define (add-grob-definition grob-name grob-entry)
   (set! all-grob-descriptions
         (cons ((@@ (lily) completize-grob-entry)
                (cons grob-name grob-entry))
               all-grob-descriptions)))

#(define (jianpu-grace-curve-stencil grob)
   (let* ((elts (ly:grob-object grob 'elements))
          (refp-X (ly:grob-common-refpoint-of-array grob elts X))
          (X-ext (ly:relative-group-extent elts refp-X X))
          (refp-Y (ly:grob-common-refpoint-of-array grob elts Y))
          (Y-ext (ly:relative-group-extent elts refp-Y Y))
          (direction (ly:grob-property grob 'direction RIGHT))
          (x-start (* 0.5 (+ (car X-ext) (cdr X-ext))))
          (y-start (+ (car Y-ext) 0.32))
          (x-start2 (if (eq? direction RIGHT)(+ x-start 0.5)(- x-start 0.5)))
          (x-end (if (eq? direction RIGHT)(+ (cdr X-ext) 0.2)(- (car X-ext) 0.2)))
          (y-end (- y-start 0.5))
          (stil (ly:make-stencil `(path 0.1
                                        (moveto ,x-start ,y-start
                                         curveto ,x-start ,y-end ,x-start ,y-end ,x-start2 ,y-end
                                         lineto ,x-end ,y-end))
                                  X-ext
                                  Y-ext))
          (offset (ly:grob-relative-coordinate grob refp-X X)))
     (ly:stencil-translate-axis stil (- offset) X)))

#(add-grob-definition
  'JianpuGraceCurve
  `(
     (stencil . ,jianpu-grace-curve-stencil)
     (meta . ((class . Spanner)
              (interfaces . ())))))

#(define jianpu-grace-curve-types
   '(
      (JianpuGraceCurveEvent
       . ((description . "Used to signal where curve encompassing music start and stop.")
          (types . (general-music jianpu-grace-curve-event span-event event))
          ))
      ))

#(set!
  jianpu-grace-curve-types
  (map (lambda (x)
         (set-object-property! (car x)
           'music-description
           (cdr (assq 'description (cdr x))))
         (let ((lst (cdr x)))
           (set! lst (assoc-set! lst 'name (car x)))
           (set! lst (assq-remove! lst 'description))
           (hashq-set! music-name-to-property-table (car x) lst)
           (cons (car x) lst)))
    jianpu-grace-curve-types))

#(set! music-descriptions
       (append jianpu-grace-curve-types music-descriptions))

#(set! music-descriptions
       (sort music-descriptions alist<?))


#(define (add-bound-item spanner item)
   (if (null? (ly:spanner-bound spanner LEFT))
       (ly:spanner-set-bound! spanner LEFT item)
       (ly:spanner-set-bound! spanner RIGHT item)))

jianpuGraceCurveEngraver =
#(lambda (context)
   (let ((span '())
         (finished '())
         (current-event '())
         (event-start '())
         (event-stop '()))
     `(
       (listeners
        (jianpu-grace-curve-event .
          ,(lambda (engraver event)
             (if (= START (ly:event-property event 'span-direction))
                 (set! event-start event)
                 (set! event-stop event)))))

       (acknowledgers
        (note-column-interface .
          ,(lambda (engraver grob source-engraver)
             (if (ly:spanner? span)
                 (begin
                  (ly:pointer-group-interface::add-grob span 'elements grob)
                  (add-bound-item span grob)))
             (if (ly:spanner? finished)
                 (begin
                  (ly:pointer-group-interface::add-grob finished 'elements grob)
                  (add-bound-item finished grob)))))
        (inline-accidental-interface .
          ,(lambda (engraver grob source-engraver)
             (if (ly:spanner? span)
                 (begin
                  (ly:pointer-group-interface::add-grob span 'elements grob)))
             (if (ly:spanner? finished)
                 (ly:pointer-group-interface::add-grob finished 'elements grob))))
        (script-interface .
          ,(lambda (engraver grob source-engraver)
             (let ((is-dyn (or (grob::has-interface grob 'dynamic-interface)
                       (eq? (ly:grob-property grob 'meta) 'DynamicText))))
               (if (and (ly:spanner? span) (not is-dyn))
                (ly:pointer-group-interface::add-grob span 'elements grob))
               (if (and (ly:spanner? finished) (not is-dyn))
                (ly:pointer-group-interface::add-grob finished 'elements grob))))))
       (process-music .
         ,(lambda (trans)
            (if (ly:stream-event? event-stop)
                (if (null? span)
                    (ly:warning "No start to this curve.")
                    (begin
                     (set! finished span)
                     (ly:engraver-announce-end-grob trans finished event-start)
                     (set! span '())
                     (set! event-stop '()))))
            (if (ly:stream-event? event-start)
                (begin
                 (set! span (ly:engraver-make-grob trans 'JianpuGraceCurve event-start))
                 (set! event-start '())))))
       
       (stop-translation-timestep .
         ,(lambda (trans)
            (if (and (ly:spanner? span)
                     (null? (ly:spanner-bound span LEFT)))
                (ly:spanner-set-bound! span LEFT
                  (ly:context-property context 'currentMusicalColumn)))
            (if (ly:spanner? finished)
                (begin
                 (if (null? (ly:spanner-bound finished RIGHT))
                     (ly:spanner-set-bound! finished RIGHT
                       (ly:context-property context 'currentMusicalColumn)))
                 (set! finished '())
                 (set! event-start '())
                 (set! event-stop '())))))
       
       (finalize
        (lambda (trans)
          (if (ly:spanner? finished)
              (begin
               (if (null? (ly:spanner-bound finished RIGHT))
                   (set! (ly:spanner-bound finished RIGHT)
                         (ly:context-property context 'currentMusicalColumn)))
               (set! finished '())))))
       )))

jianpuGraceCurveStart =
#(make-span-event 'JianpuGraceCurveEvent START)

jianpuGraceCurveEnd =
#(make-span-event 'JianpuGraceCurveEvent STOP)
%===========================================================

%{ The jianpu-ly input was:
title=寄往未来的信
1=G
4/4
4=125
1' 1' - 1' |
1' - 2' q3' q7 |
7 q7 q7 0 7 |
0 7 q7 q1' q2' q6 |
6 q6 q6 0 6 |
0 6 q5 q6 1' |
2' 1' 0 0 |
0 0 1 2 |
5 3 2 q5 q3 |
q3 q2 q3 q2 3 5 |
5 3 2 q1 q2 |
0 q2 q1 2 3 |
6, 3 - - |
3 1 2 3 |
6, 3 - q2 q1 |
0 0 1 2 |
5 3 2 q5 q3 |
2 q3 q2 3 5 |
5 q2 q3 2 q1 q2 |
0 1 2 3 |
6, 3 - 0 |
0 1 2 q3 q#1 |
6, 2 3 q2 q1 |
0 0 0 0 |
q1 q1 2 2 q3 q3 |
0 5 4 3 |
q7, q1 q1 q1 1 q2 q2 |
0 4 q3 q2 2 |
q1 q5 3 3 - |
0 0 0 2 |
q1 q5 3 - q2 q1 |
0 1 q1 q2 3 |
0 0 1 2 |
3 q5 q5 1 q7, q7, |
0 0 7, q7, q1 |
2 q4 q3 7, q7, q1 |
0 0 0 q6, q7, |
1 q3 q3 1 q6, q6, |
6, q6, q1' 2' q5, q5, |
q4 q4 q3 q1 4 3 |
0 0 1 q1 q2 |
3 q5 q5 1 q7, q7, |
0 0 0 q7, q1 |
2 q4 q3 2 q2 q1 |
0 0 0 q6, q7, |
1 q3 q3 0 q1 q6, |
0 q6, q5, q4 q3 3 |
4 q3 q1 7, 1 |
0 0 0 0 |
0 1' 2' q3' q7 |
2' q3' q7 7 - |
0 0 q7 q1' q2' q6 |
6 q#5 q6 0 q6 q6 |
#5 6 q5 q6 1' |
2' 1' 2' 0 |
0 0 0 0 |
q1 q1 2 2 q3 q3 |
0 5 4 3 |
q7, q7, 1 1 q2 q2 |
0 4 q3 q7, 7, |
1 5 3 4 |
0 4 q3 q1 q1 q6, |
6, - 5, q6, q5, |
0 0 0 0 |
q1 q1 2 2 q3 q3 |
0 5 4 3 |
q7, q7, 1 1 q2 q1 |
2 q3 q4 3 q7, q1 |
0 5 q5 q3 0 |
0 0 0 5, |
4 q4 q4 3 4 |
3 q1 q#1 #1 1 |
0 0 q1' q1 2 |
3 q5 q5 1 q7, q7, |
0 0 7, q7, q1 |
2 q4 q3 7, q7, q1 |
0 0 0 q6, q7, |
1 q3 q3 7, q6, q6, |
6, q6, q1' 0 q5, q5, |
4 q3 q1 q3 q4 3 |
0 0 1 q1 q2 |
3 q5 q5 1 q7, q7, |
0 0 0 q7, q1 |
2 q4 q3 2 q2 q1 |
0 0 0 q6, q7, |
1 q3 q3 0 q1 q6, |
0 q6, q5, q4 q3 3 |
4 q3 q1 #2 3 |
3 0 1 q1 q2 |
3 q5 q5 q5 q1 q7, q7, |
0 0 7, q7, q1 |
2 q4 q3 q3 q3 q7, q1 |
0 0 0 q6, q7, |
1 q3 q3 q3 q7, q#5, q6, |
q#5, q1' 6, 0 q1 q1, |
6 q4 q4 6 4 |
#4 5 3 q3 q3 |
3 q1 q1 3 q2 q2 |
2 - - q#2 q3 |
3 q5 s6 s3 q5 q2 3 |
0 0 0 q#1 q3 |
3 q3 q3 q#4 q3 q3, q1 |
0 q#5, q5, 3 3 |
4 q3 q1 7, 0 |
%}


\score {
<< \override Score.BarNumber #'break-visibility = #center-visible
\override Score.BarNumber #'Y-offset = -1
\set Score.barNumberVisibility = #(every-nth-bar-number-visible 5)

%% === BEGIN JIANPU STAFF ===
    \new RhythmicStaff \with {
    \consists "Accidental_engraver" 
    \consists \jianpuGraceCurveEngraver
    \override Glissando.before-line-breaking = #jianpu-glissando
    % Get rid of the stave but not the barlines:
    \override StaffSymbol #'line-count = #0 % tested in 2.15.40, 2.16.2, 2.18.0, 2.18.2, 2.20.0 and 2.22.2
    \override BarLine #'bar-extent = #'(-2 . 2) % LilyPond 2.18: please make barlines as high as the time signature even though we're on a RhythmicStaff (2.16 and 2.15 don't need this although its presence doesn't hurt; Issue 3685 seems to indicate they'll fix it post-2.18)
    $(add-grace-property 'Voice 'Stem 'direction DOWN)
    $(add-grace-property 'Voice 'Slur 'direction UP)
    $(add-grace-property 'Voice 'Stem 'length-fraction 0.5)
    $(add-grace-property 'Voice 'Beam 'beam-thickness 0.1)
    $(add-grace-property 'Voice 'Beam 'length-fraction 0.3)
    $(add-grace-property 'Voice 'Beam 'after-line-breaking flip-beams)
    $(add-grace-property 'Voice 'Beam 'Y-offset 2.5)
    $(add-grace-property 'Voice 'NoteHead 'Y-offset 2.5)
    }
    { \new Voice="W" {
    \override Beam #'transparent = ##f
    \override Stem #'direction = #DOWN
    \override Tie #'staff-position = #2.5
    \tupletUp
    \tieUp
    \override Stem #'length-fraction = #0.5
    \override Beam #'beam-thickness = #0.1
    \override Beam #'length-fraction = #0.5
    \override Beam.after-line-breaking = #flip-beams
    \override Voice.Rest #'style = #'neomensural % this size tends to line up better (we'll override the appearance anyway)
    \override Accidental #'font-size = #-4
    \override TupletBracket #'bracket-visibility = ##t

    \override Staff.TimeSignature #'style = #'numbered
    \override Staff.Stem #'transparent = ##t
     \mark \markup{1=G} \time 4/4 \tempo 4=125  \note-mod "1" c''4^. \once \override Tie #'transparent = ##t \once \override Tie #'staff-position = #0  \note-mod "1" c''4^.
 ~  \note-mod "–" c''4  \note-mod "1" c''4^. | \once \override Tie #'transparent = ##t \once \override Tie #'staff-position = #0 | %{ bar 2: %}
 \note-mod "1" c''4^.
 ~  \note-mod "–" c''4  \note-mod "2" d''4^. \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e''8^.[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "7" b'8]
| | %{ bar 3: %}
 \note-mod "7" b'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "7" b'8]
 \note-mod "0" r4  \note-mod "7" b'4 | | %{ bar 4: %}
 \note-mod "0" r4
 \note-mod "7" b'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c''8^.]
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "2" d''8^.[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "6" a'8]
| | %{ bar 5: %}
 \note-mod "6" a'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "6" a'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "6" a'8]
 \note-mod "0" r4  \note-mod "6" a'4 | | %{ bar 6: %}
 \note-mod "0" r4
 \note-mod "6" a'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "5" g'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "6" a'8]
 \note-mod "1" c''4^. | | %{ bar 7: %}
 \note-mod "2" d''4^.
 \note-mod "1" c''4^.  \note-mod "0" r4  \note-mod "0" r4 | | %{ bar 8: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "1" c'4  \note-mod "2" d'4 | | %{ bar 9: %}
 \note-mod "5" g'4
 \note-mod "3" e'4  \note-mod "2" d'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "5" g'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
| | %{ bar 10: %} \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "2" d'8]
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "2" d'8]
 \note-mod "3" e'4  \note-mod "5" g'4 | | %{ bar 11: %}
 \note-mod "5" g'4
 \note-mod "3" e'4  \note-mod "2" d'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "1" c'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "2" d'8]
| | %{ bar 12: %}
 \note-mod "0" r4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "2" d'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
 \note-mod "2" d'4  \note-mod "3" e'4 | | %{ bar 13: %}
 \note-mod "6" a4-\tweak #'Y-offset #-1.2 -\tweak #'X-offset #0.6 _. 
\once \override Tie #'transparent = ##t \once \override Tie #'staff-position = #0  \note-mod "3" e'4
 ~ \once \override Tie #'transparent = ##t \once \override Tie #'staff-position = #0  \note-mod "–" e'4
 ~  \note-mod "–" e'4 | | %{ bar 14: %}
 \note-mod "3" e'4
 \note-mod "1" c'4  \note-mod "2" d'4  \note-mod "3" e'4 | | %{ bar 15: %}
 \note-mod "6" a4-\tweak #'Y-offset #-1.2 -\tweak #'X-offset #0.6 _. 
\once \override Tie #'transparent = ##t \once \override Tie #'staff-position = #0  \note-mod "3" e'4
 ~  \note-mod "–" e'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "2" d'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
| | %{ bar 16: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "1" c'4  \note-mod "2" d'4 | | %{ bar 17: %}
 \note-mod "5" g'4
 \note-mod "3" e'4  \note-mod "2" d'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "5" g'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
| | %{ bar 18: %}
 \note-mod "2" d'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "2" d'8]
 \note-mod "3" e'4  \note-mod "5" g'4 | | %{ bar 19: %}
 \note-mod "5" g'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "2" d'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
 \note-mod "2" d'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "1" c'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "2" d'8]
| | %{ bar 20: %}
 \note-mod "0" r4
 \note-mod "1" c'4  \note-mod "2" d'4  \note-mod "3" e'4 | | %{ bar 21: %}
 \note-mod "6" a4-\tweak #'Y-offset #-1.2 -\tweak #'X-offset #0.6 _. 
\once \override Tie #'transparent = ##t \once \override Tie #'staff-position = #0  \note-mod "3" e'4
 ~  \note-mod "–" e'4  \note-mod "0" r4 | | %{ bar 22: %}
 \note-mod "0" r4
 \note-mod "1" c'4  \note-mod "2" d'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" \once \tweak Accidental.extra-offset #'(0 . 0.7)cis'8]
| | %{ bar 23: %}
 \note-mod "6" a4-\tweak #'Y-offset #-1.2 -\tweak #'X-offset #0.6 _. 
 \note-mod "2" d'4  \note-mod "3" e'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "2" d'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
| | %{ bar 24: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "0" r4  \note-mod "0" r4 | | %{ bar 25: %} \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "1" c'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
 \note-mod "2" d'4  \note-mod "2" d'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
| | %{ bar 26: %}
 \note-mod "0" r4
 \note-mod "5" g'4  \note-mod "4" f'4  \note-mod "3" e'4 | | %{ bar 27: %} \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "1" c'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
 \note-mod "1" c'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "2" d'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "2" d'8]
| | %{ bar 28: %}
 \note-mod "0" r4
 \note-mod "4" f'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "2" d'8]
 \note-mod "2" d'4 | | %{ bar 29: %} \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "1" c'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "5" g'8]
 \note-mod "3" e'4 \once \override Tie #'transparent = ##t \once \override Tie #'staff-position = #0  \note-mod "3" e'4
 ~  \note-mod "–" e'4 | | %{ bar 30: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "0" r4  \note-mod "2" d'4 | | %{ bar 31: %} \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "1" c'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "5" g'8]
\once \override Tie #'transparent = ##t \once \override Tie #'staff-position = #0  \note-mod "3" e'4
 ~  \note-mod "–" e'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "2" d'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
| | %{ bar 32: %}
 \note-mod "0" r4
 \note-mod "1" c'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "1" c'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "2" d'8]
 \note-mod "3" e'4 | | %{ bar 33: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "1" c'4  \note-mod "2" d'4 | | %{ bar 34: %}
 \note-mod "3" e'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "5" g'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "5" g'8]
 \note-mod "1" c'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. ]
| | %{ bar 35: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "7" b4-\tweak #'Y-offset #-1.2 -\tweak #'X-offset #0.6 _. 
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
| | %{ bar 36: %}
 \note-mod "2" d'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "4" f'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
 \note-mod "7" b4-\tweak #'Y-offset #-1.2 -\tweak #'X-offset #0.6 _. 
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
| | %{ bar 37: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "0" r4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "6" a8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. ]
| | %{ bar 38: %}
 \note-mod "1" c'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
 \note-mod "1" c'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "6" a8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "6" a8-\tweak #'X-offset #0.6 _. ]
| | %{ bar 39: %}
 \note-mod "6" a4-\tweak #'Y-offset #-1.2 -\tweak #'X-offset #0.6 _. 
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "6" a8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c''8^.]
 \note-mod "2" d''4^. \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "5" g8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "5" g8-\tweak #'X-offset #0.6 _. ]
| | %{ bar 40: %} \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "4" f'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "4" f'8]
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
 \note-mod "4" f'4  \note-mod "3" e'4 | | %{ bar 41: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "1" c'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "1" c'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "2" d'8]
| | %{ bar 42: %}
 \note-mod "3" e'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "5" g'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "5" g'8]
 \note-mod "1" c'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. ]
| | %{ bar 43: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "0" r4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
| | %{ bar 44: %}
 \note-mod "2" d'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "4" f'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
 \note-mod "2" d'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "2" d'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
| | %{ bar 45: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "0" r4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "6" a8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. ]
| | %{ bar 46: %}
 \note-mod "1" c'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
 \note-mod "0" r4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "1" c'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "6" a8-\tweak #'X-offset #0.6 _. ]
| | %{ bar 47: %}
 \note-mod "0" r4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "6" a8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "5" g8-\tweak #'X-offset #0.6 _. ]
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "4" f'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
 \note-mod "3" e'4 | | %{ bar 48: %}
 \note-mod "4" f'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
 \note-mod "7" b4-\tweak #'Y-offset #-1.2 -\tweak #'X-offset #0.6 _. 
 \note-mod "1" c'4 | | %{ bar 49: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "0" r4  \note-mod "0" r4 | | %{ bar 50: %}
 \note-mod "0" r4
 \note-mod "1" c''4^.  \note-mod "2" d''4^. \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e''8^.[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "7" b'8]
| | %{ bar 51: %}
 \note-mod "2" d''4^.
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e''8^.[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "7" b'8]
\once \override Tie #'transparent = ##t \once \override Tie #'staff-position = #0  \note-mod "7" b'4
 ~  \note-mod "–" b'4 | | %{ bar 52: %}
 \note-mod "0" r4
 \note-mod "0" r4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c''8^.]
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "2" d''8^.[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "6" a'8]
| | %{ bar 53: %}
 \note-mod "6" a'4
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "5" \once \tweak Accidental.extra-offset #'(0 . 0.7)gis'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "6" a'8]
 \note-mod "0" r4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "6" a'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "6" a'8]
| | %{ bar 54: %}
 \note-mod "5" \once \tweak Accidental.extra-offset #'(0 . 0.7)gis'4
 \note-mod "6" a'4 \set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "5" \once \tweak Accidental.extra-offset #'(0 . 0.7)g'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "6" a'8]
 \note-mod "1" c''4^. | | %{ bar 55: %}
 \note-mod "2" d''4^.
 \note-mod "1" c''4^.  \note-mod "2" d''4^.  \note-mod "0" r4 | | %{ bar 56: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "0" r4  \note-mod "0" r4 | | %{ bar 57: %} \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "1" c'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
 \note-mod "2" d'4  \note-mod "2" d'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
| | %{ bar 58: %}
 \note-mod "0" r4
 \note-mod "5" g'4  \note-mod "4" f'4  \note-mod "3" e'4 | | %{ bar 59: %} \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. ]
 \note-mod "1" c'4  \note-mod "1" c'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "2" d'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "2" d'8]
| | %{ bar 60: %}
 \note-mod "0" r4
 \note-mod "4" f'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. ]
 \note-mod "7" b4-\tweak #'Y-offset #-1.2 -\tweak #'X-offset #0.6 _. 
| | %{ bar 61: %}
 \note-mod "1" c'4
 \note-mod "5" g'4  \note-mod "3" e'4  \note-mod "4" f'4 | | %{ bar 62: %}
 \note-mod "0" r4
 \note-mod "4" f'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "1" c'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "6" a8-\tweak #'X-offset #0.6 _. ]
| \once \override Tie #'transparent = ##t \once \override Tie #'staff-position = #0 | %{ bar 63: %}
 \note-mod "6" a4-\tweak #'Y-offset #-1.2 -\tweak #'X-offset #0.6 _. 
 ~  \note-mod "–" a4  \note-mod "5" g4-\tweak #'Y-offset #-1.2 -\tweak #'X-offset #0.6 _. 
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "6" a8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "5" g8-\tweak #'X-offset #0.6 _. ]
| | %{ bar 64: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "0" r4  \note-mod "0" r4 | | %{ bar 65: %} \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "1" c'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
 \note-mod "2" d'4  \note-mod "2" d'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
| | %{ bar 66: %}
 \note-mod "0" r4
 \note-mod "5" g'4  \note-mod "4" f'4  \note-mod "3" e'4 | | %{ bar 67: %} \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. ]
 \note-mod "1" c'4  \note-mod "1" c'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "2" d'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
| | %{ bar 68: %}
 \note-mod "2" d'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "4" f'8]
 \note-mod "3" e'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
| | %{ bar 69: %}
 \note-mod "0" r4
 \note-mod "5" g'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "5" g'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
 \note-mod "0" r4 | | %{ bar 70: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "0" r4  \note-mod "5" g4-\tweak #'Y-offset #-1.2 -\tweak #'X-offset #0.6 _. 
| | %{ bar 71: %}
 \note-mod "4" f'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "4" f'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "4" f'8]
 \note-mod "3" e'4  \note-mod "4" f'4 | | %{ bar 72: %}
 \note-mod "3" e'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "1" c'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" \once \tweak Accidental.extra-offset #'(0 . 0.7)cis'8]
 \note-mod "1" cis'4  \note-mod "1" \once \tweak Accidental.extra-offset #'(0 . 0.7)c'4
| | %{ bar 73: %}
 \note-mod "0" r4
 \note-mod "0" r4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "1" c''8^.[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
 \note-mod "2" d'4 | | %{ bar 74: %}
 \note-mod "3" e'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "5" g'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "5" g'8]
 \note-mod "1" c'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. ]
| | %{ bar 75: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "7" b4-\tweak #'Y-offset #-1.2 -\tweak #'X-offset #0.6 _. 
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
| | %{ bar 76: %}
 \note-mod "2" d'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "4" f'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
 \note-mod "7" b4-\tweak #'Y-offset #-1.2 -\tweak #'X-offset #0.6 _. 
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
| | %{ bar 77: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "0" r4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "6" a8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. ]
| | %{ bar 78: %}
 \note-mod "1" c'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
 \note-mod "7" b4-\tweak #'Y-offset #-1.2 -\tweak #'X-offset #0.6 _. 
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "6" a8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "6" a8-\tweak #'X-offset #0.6 _. ]
| | %{ bar 79: %}
 \note-mod "6" a4-\tweak #'Y-offset #-1.2 -\tweak #'X-offset #0.6 _. 
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "6" a8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c''8^.]
 \note-mod "0" r4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "5" g8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "5" g8-\tweak #'X-offset #0.6 _. ]
| | %{ bar 80: %}
 \note-mod "4" f'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "4" f'8]
 \note-mod "3" e'4 | | %{ bar 81: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "1" c'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "1" c'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "2" d'8]
| | %{ bar 82: %}
 \note-mod "3" e'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "5" g'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "5" g'8]
 \note-mod "1" c'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. ]
| | %{ bar 83: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "0" r4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
| | %{ bar 84: %}
 \note-mod "2" d'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "4" f'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
 \note-mod "2" d'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "2" d'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
| | %{ bar 85: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "0" r4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "6" a8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. ]
| | %{ bar 86: %}
 \note-mod "1" c'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
 \note-mod "0" r4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "1" c'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "6" a8-\tweak #'X-offset #0.6 _. ]
| | %{ bar 87: %}
 \note-mod "0" r4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "6" a8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "5" g8-\tweak #'X-offset #0.6 _. ]
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "4" f'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
 \note-mod "3" e'4 | | %{ bar 88: %}
 \note-mod "4" f'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
 \note-mod "2" \once \tweak Accidental.extra-offset #'(0 . 0.7)dis'4
 \note-mod "3" e'4 | | %{ bar 89: %}
 \note-mod "3" e'4
 \note-mod "0" r4  \note-mod "1" c'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "1" c'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "2" d'8]
| | %{ bar 90: %}
 \note-mod "3" e'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "5" g'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "5" g'8]
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "5" g'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. ]
| | %{ bar 91: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "7" b4-\tweak #'Y-offset #-1.2 -\tweak #'X-offset #0.6 _. 
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
| | %{ bar 92: %}
 \note-mod "2" d'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "4" f'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
| | %{ bar 93: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "0" r4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "6" a8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. ]
| | %{ bar 94: %}
 \note-mod "1" c'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "7" b8-\tweak #'X-offset #0.6 _. ]
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "5" \once \tweak Accidental.extra-offset #'(0 . 0.7)gis8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "6" a8-\tweak #'X-offset #0.6 _. ]
| | %{ bar 95: %} \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "5" \once \tweak Accidental.extra-offset #'(0 . 0.7)gis8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c''8^.]
 \note-mod "6" a4-\tweak #'Y-offset #-1.2 -\tweak #'X-offset #0.6 _. 
 \note-mod "0" r4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "1" c'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c8-\tweak #'X-offset #0.6 _. ]
| | %{ bar 96: %}
 \note-mod "6" a'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "4" f'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "4" f'8]
 \note-mod "6" a'4  \note-mod "4" f'4 | | %{ bar 97: %}
 \note-mod "4" \once \tweak Accidental.extra-offset #'(0 . 0.7)fis'4
 \note-mod "5" g'4  \note-mod "3" e'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
| | %{ bar 98: %}
 \note-mod "3" e'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "1" c'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
 \note-mod "3" e'4 \set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "2" d'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "2" d'8]
| \once \override Tie #'transparent = ##t \once \override Tie #'staff-position = #0 | %{ bar 99: %}
 \note-mod "2" d'4
 ~ \once \override Tie #'transparent = ##t \once \override Tie #'staff-position = #0  \note-mod "–" d'4
 ~  \note-mod "–" d'4 \set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "2" \once \tweak Accidental.extra-offset #'(0 . 0.7)dis'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
| | %{ bar 100: %}
 \note-mod "3" e'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "5" g'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #2
 \note-mod "6" a'16
\set stemLeftBeamCount = #2
\set stemRightBeamCount = #2
 \note-mod "3" e'16]
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "5" g'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "2" d'8]
 \note-mod "3" e'4 | | %{ bar 101: %}
 \note-mod "0" r4
 \note-mod "0" r4  \note-mod "0" r4 \set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" \once \tweak Accidental.extra-offset #'(0 . 0.7)cis'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
| | %{ bar 102: %}
 \note-mod "3" e'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "4" \once \tweak Accidental.extra-offset #'(0 . 0.7)fis'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "3" e'8]
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
| | %{ bar 103: %}
 \note-mod "0" r4
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "5" \once \tweak Accidental.extra-offset #'(0 . 0.7)gis8-\tweak #'X-offset #0.6 _. [
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "5" \once \tweak Accidental.extra-offset #'(0 . 0.7)g8-\tweak #'X-offset #0.6 _. ]
 \note-mod "3" e'4  \note-mod "3" e'4 | | %{ bar 104: %}
 \note-mod "4" f'4
\set stemLeftBeamCount = #0
\set stemRightBeamCount = #1
 \note-mod "3" e'8[
\set stemLeftBeamCount = #1
\set stemRightBeamCount = #1
 \note-mod "1" c'8]
 \note-mod "7" b4-\tweak #'Y-offset #-1.2 -\tweak #'X-offset #0.6 _. 
 \note-mod "0" r4 | \bar "|." } }
% === END JIANPU STAFF ===

>>
\header{
title="寄往未来的信"
}
\layout{
  \context {
    \Global
    \grobdescriptions #all-grob-descriptions
  }
} }
\score {
\unfoldRepeats
<< 

% === BEGIN MIDI STAFF ===
    \new Staff { \new Voice="X" { \transpose c g, { \key c \major  \time 4/4 \tempo 4=125 c''4 c''2 c''4 | | %{ bar 2: %} c''2 d''4 e''8 b'8 | | %{ bar 3: %} b'4 b'8 b'8 r4 b'4 | | %{ bar 4: %} r4 b'4 b'8 c''8 d''8 a'8 | | %{ bar 5: %} a'4 a'8 a'8 r4 a'4 | | %{ bar 6: %} r4 a'4 g'8 a'8 c''4 | | %{ bar 7: %} d''4 c''4 r2 | | %{ bar 8: %} r2 c'4 d'4 | | %{ bar 9: %} g'4 e'4 d'4 g'8 e'8 | | %{ bar 10: %} e'8 d'8 e'8 d'8 e'4 g'4 | | %{ bar 11: %} g'4 e'4 d'4 c'8 d'8 | | %{ bar 12: %} r4 d'8 c'8 d'4 e'4 | | %{ bar 13: %} a4 e'2. | | %{ bar 14: %} e'4 c'4 d'4 e'4 | | %{ bar 15: %} a4 e'2 d'8 c'8 | | %{ bar 16: %} r2 c'4 d'4 | | %{ bar 17: %} g'4 e'4 d'4 g'8 e'8 | | %{ bar 18: %} d'4 e'8 d'8 e'4 g'4 | | %{ bar 19: %} g'4 d'8 e'8 d'4 c'8 d'8 | | %{ bar 20: %} r4 c'4 d'4 e'4 | | %{ bar 21: %} a4 e'2 r4 | | %{ bar 22: %} r4 c'4 d'4 e'8 cis'8 | | %{ bar 23: %} a4 d'4 e'4 d'8 c'8 | | %{ bar 24: %} R1 | | %{ bar 25: %} c'8 c'8 d'4 d'4 e'8 e'8 | | %{ bar 26: %} r4 g'4 f'4 e'4 | | %{ bar 27: %} b8 c'8 c'8 c'8 c'4 d'8 d'8 | | %{ bar 28: %} r4 f'4 e'8 d'8 d'4 | | %{ bar 29: %} c'8 g'8 e'4 e'2 | | %{ bar 30: %} r2. d'4 | | %{ bar 31: %} c'8 g'8 e'2 d'8 c'8 | | %{ bar 32: %} r4 c'4 c'8 d'8 e'4 | | %{ bar 33: %} r2 c'4 d'4 | | %{ bar 34: %} e'4 g'8 g'8 c'4 b8 b8 | | %{ bar 35: %} r2 b4 b8 c'8 | | %{ bar 36: %} d'4 f'8 e'8 b4 b8 c'8 | | %{ bar 37: %} r2. a8 b8 | | %{ bar 38: %} c'4 e'8 e'8 c'4 a8 a8 | | %{ bar 39: %} a4 a8 c''8 d''4 g8 g8 | | %{ bar 40: %} f'8 f'8 e'8 c'8 f'4 e'4 | | %{ bar 41: %} r2 c'4 c'8 d'8 | | %{ bar 42: %} e'4 g'8 g'8 c'4 b8 b8 | | %{ bar 43: %} r2. b8 c'8 | | %{ bar 44: %} d'4 f'8 e'8 d'4 d'8 c'8 | | %{ bar 45: %} r2. a8 b8 | | %{ bar 46: %} c'4 e'8 e'8 r4 c'8 a8 | | %{ bar 47: %} r4 a8 g8 f'8 e'8 e'4 | | %{ bar 48: %} f'4 e'8 c'8 b4 c'4 | | %{ bar 49: %} R1 | | %{ bar 50: %} r4 c''4 d''4 e''8 b'8 | | %{ bar 51: %} d''4 e''8 b'8 b'2 | | %{ bar 52: %} r2 b'8 c''8 d''8 a'8 | | %{ bar 53: %} a'4 gis'8 a'8 r4 a'8 a'8 | | %{ bar 54: %} gis'4 a'4 g'8 a'8 c''4 | | %{ bar 55: %} d''4 c''4 d''4 r4 | | %{ bar 56: %} R1 | | %{ bar 57: %} c'8 c'8 d'4 d'4 e'8 e'8 | | %{ bar 58: %} r4 g'4 f'4 e'4 | | %{ bar 59: %} b8 b8 c'4 c'4 d'8 d'8 | | %{ bar 60: %} r4 f'4 e'8 b8 b4 | | %{ bar 61: %} c'4 g'4 e'4 f'4 | | %{ bar 62: %} r4 f'4 e'8 c'8 c'8 a8 | | %{ bar 63: %} a2 g4 a8 g8 | | %{ bar 64: %} R1 | | %{ bar 65: %} c'8 c'8 d'4 d'4 e'8 e'8 | | %{ bar 66: %} r4 g'4 f'4 e'4 | | %{ bar 67: %} b8 b8 c'4 c'4 d'8 c'8 | | %{ bar 68: %} d'4 e'8 f'8 e'4 b8 c'8 | | %{ bar 69: %} r4 g'4 g'8 e'8 r4 | | %{ bar 70: %} r2. g4 | | %{ bar 71: %} f'4 f'8 f'8 e'4 f'4 | | %{ bar 72: %} e'4 c'8 cis'8 cis'4 c'4 | | %{ bar 73: %} r2 c''8 c'8 d'4 | | %{ bar 74: %} e'4 g'8 g'8 c'4 b8 b8 | | %{ bar 75: %} r2 b4 b8 c'8 | | %{ bar 76: %} d'4 f'8 e'8 b4 b8 c'8 | | %{ bar 77: %} r2. a8 b8 | | %{ bar 78: %} c'4 e'8 e'8 b4 a8 a8 | | %{ bar 79: %} a4 a8 c''8 r4 g8 g8 | | %{ bar 80: %} f'4 e'8 c'8 e'8 f'8 e'4 | | %{ bar 81: %} r2 c'4 c'8 d'8 | | %{ bar 82: %} e'4 g'8 g'8 c'4 b8 b8 | | %{ bar 83: %} r2. b8 c'8 | | %{ bar 84: %} d'4 f'8 e'8 d'4 d'8 c'8 | | %{ bar 85: %} r2. a8 b8 | | %{ bar 86: %} c'4 e'8 e'8 r4 c'8 a8 | | %{ bar 87: %} r4 a8 g8 f'8 e'8 e'4 | | %{ bar 88: %} f'4 e'8 c'8 dis'4 e'4 | | %{ bar 89: %} e'4 r4 c'4 c'8 d'8 | | %{ bar 90: %} e'4 g'8 g'8 g'8 c'8 b8 b8 | | %{ bar 91: %} r2 b4 b8 c'8 | | %{ bar 92: %} d'4 f'8 e'8 e'8 e'8 b8 c'8 | | %{ bar 93: %} r2. a8 b8 | | %{ bar 94: %} c'4 e'8 e'8 e'8 b8 gis8 a8 | | %{ bar 95: %} gis8 c''8 a4 r4 c'8 c8 | | %{ bar 96: %} a'4 f'8 f'8 a'4 f'4 | | %{ bar 97: %} fis'4 g'4 e'4 e'8 e'8 | | %{ bar 98: %} e'4 c'8 c'8 e'4 d'8 d'8 | | %{ bar 99: %} d'2. dis'8 e'8 | | %{ bar 100: %} e'4 g'8 a'16 e'16 g'8 d'8 e'4 | | %{ bar 101: %} r2. cis'8 e'8 | | %{ bar 102: %} e'4 e'8 e'8 fis'8 e'8 e8 c'8 | | %{ bar 103: %} r4 gis8 g8 e'4 e'4 | | %{ bar 104: %} f'4 e'8 c'8 b4 r4 | } } }
% === END MIDI STAFF ===

>>
\header{
title="寄往未来的信"
}
\midi { \context { \Score tempoWholesPerMinute = #(ly:make-moment 84 4)}} }
