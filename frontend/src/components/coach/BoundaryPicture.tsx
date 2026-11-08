import { ELBOW, FIGURE, KNEE, elbowHand, heightWrist, kneeHip } from "@/lib/coach";

type Props = {
  set: string;
  value: number;
  selected?: boolean;
};

/** Picture for one boundary choice, drawn from the same value the rule uses. */
export function BoundaryPicture({ set, value, selected = false }: Props) {
  const limb = selected ? "stroke-accent" : "stroke-text-soft";
  return (
    <svg width="90" height="108" viewBox="0 0 100 120" fill="none" aria-hidden="true">
      {set === "elbow_angle" && <ElbowShape value={value} limb={limb} />}
      {set === "knee_angle" && <KneeShape value={value} limb={limb} />}
      {set === "hand_height" && <HeightShape value={value} limb={limb} />}
    </svg>
  );
}

function Joint({ x, y }: { x: number; y: number }) {
  return <circle cx={x} cy={y} r="5" className="fill-bg stroke-text" strokeWidth="2.5" />;
}

function ElbowShape({ value, limb }: { value: number; limb: string }) {
  const hand = elbowHand(value);
  return (
    <>
      <path
        d={`M${ELBOW.shoulder.x} ${ELBOW.shoulder.y} V${ELBOW.elbow.y}`}
        className="stroke-text-soft"
        strokeWidth="7"
        strokeLinecap="round"
      />
      <path
        data-testid="forearm"
        d={`M${ELBOW.elbow.x} ${ELBOW.elbow.y} L${hand.x.toFixed(1)} ${hand.y.toFixed(1)}`}
        className={limb}
        strokeWidth="7"
        strokeLinecap="round"
      />
      <Joint {...ELBOW.elbow} />
    </>
  );
}

function KneeShape({ value, limb }: { value: number; limb: string }) {
  const hip = kneeHip(value);
  return (
    <>
      <path
        d={`M${KNEE.ankle.x} ${KNEE.ankle.y} V${KNEE.knee.y}`}
        className="stroke-text-soft"
        strokeWidth="7"
        strokeLinecap="round"
      />
      <path
        d={`M${KNEE.ankle.x} ${KNEE.ankle.y} h-16`}
        className="stroke-text-soft"
        strokeWidth="6"
        strokeLinecap="round"
      />
      <path
        data-testid="thigh"
        d={`M${KNEE.knee.x} ${KNEE.knee.y} L${hip.x.toFixed(1)} ${hip.y.toFixed(1)}`}
        className={limb}
        strokeWidth="7"
        strokeLinecap="round"
      />
      <Joint {...KNEE.knee} />
    </>
  );
}

function HeightShape({ value, limb }: { value: number; limb: string }) {
  const { shoulder, torso } = FIGURE;
  const hip = { x: shoulder.x, y: shoulder.y + torso };
  const wrist = heightWrist(value);
  return (
    <>
      <path
        d={`M4 ${wrist.y.toFixed(1)} H96`}
        className="stroke-border"
        strokeWidth="1.5"
        strokeDasharray="4 4"
      />
      <circle cx={shoulder.x} cy={shoulder.y - 15} r="8" className="stroke-text-soft" strokeWidth="2.5" />
      <path
        d={`M${shoulder.x} ${shoulder.y} V${hip.y} M${hip.x} ${hip.y} l-8 26 M${hip.x} ${hip.y} l8 26`}
        className="stroke-text-soft"
        strokeWidth="4"
        strokeLinecap="round"
      />
      <path
        data-testid="arm"
        d={`M${shoulder.x} ${shoulder.y} L${wrist.x.toFixed(1)} ${wrist.y.toFixed(1)}`}
        className={limb}
        strokeWidth="5"
        strokeLinecap="round"
      />
      <circle cx={wrist.x} cy={wrist.y} r="4" className="fill-warn" />
    </>
  );
}
