import Link from "next/link";
import Image from "next/image";

interface BrandProps {
  className?: string;
  size?: "sm" | "md" | "lg";
  variant?: "horizontal" | "stacked" | "icon";
  ariaLabel?: string;
}

export function Brand({
  className = "",
  size = "md",
  variant = "horizontal",
  ariaLabel = "Cyberoom home",
}: BrandProps) {
  const isHorizontal = variant === "horizontal";
  const isIcon = variant === "icon";

  const height = size === "sm" ? 26 : size === "lg" ? 48 : 36;
  const width = isHorizontal
    ? Math.round(height * 3.93)
    : isIcon
    ? Math.round(height * 1.37)
    : Math.round(height * 1.1);

  const src = isIcon
    ? "/logo-icon.png"
    : isHorizontal
    ? "/logo-horizontal.png"
    : "/logo.png";

  return (
    <Link
      className={`brand brand-${size} brand-${variant} ${className}`}
      href="/"
      aria-label={ariaLabel}
    >
      <Image
        src={src}
        alt="Cyberoom"
        width={width}
        height={height}
        priority={size !== "sm"}
        className="brand-logo"
      />
    </Link>
  );
}
